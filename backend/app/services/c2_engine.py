# backend/app/services/c2_engine.py
import asyncio
import json
import logging
import math
import random
import time
from datetime import datetime
from typing import Dict, List
import numpy as np
from shapely.geometry import Point, Polygon
from sqlalchemy import select, desc, func

from app.config import settings
from app.database import async_session
from app.models import EWNodeModel, TacticalZoneModel, TacticalSensorModel, DownedDroneModel
from app.core.geo import latlon_to_enu, enu_to_latlon, calculate_azimuth_elevation
from app.core.kalman import DroneKalmanFilter
from app.core.planner import InterceptionPlanner
from app.core.risk_h3 import safety_at_enu as risk_safety_at_enu
from app.hardware.pelco import PelcoDController
from app.services.simulation import DroneSimulation
from app.services.connection_manager import ws_manager
from app.seed.settlement_sensors import SETTLEMENT_HUBS

logger = logging.getLogger(__name__)

class C2Engine:
    def __init__(self):
        self.drone = DroneSimulation()
        self.active_trackers: Dict[str, DroneKalmanFilter] = {}
        self.simulation_active: bool = True
        self.auto_tracking_enabled: bool = True
        self.sim_start_time: float = time.time()
        self._zone_cache: Dict = {"fp": None, "safe": [], "caution": [], "danger": [], "items": []}
        self._burst_generations: Dict[int, int] = {}
        self._recent_events: List[dict] = []
        self._hub_enu_cache: List[dict] = []

        # Попередній розрахунок координат населених пунктів в ENU
        for hub in SETTLEMENT_HUBS:
            hx, hy, _ = latlon_to_enu(hub["lat"], hub["lon"], 0.0)
            self._hub_enu_cache.append({
                "name": hub["name"],
                "lat": hub["lat"],
                "lon": hub["lon"],
                "x": hx,
                "y": hy
            })

    def sanitize(self, o):
        if isinstance(o, float):
            return o if math.isfinite(o) else None
        if isinstance(o, dict):
            return {k: self.sanitize(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [self.sanitize(v) for v in o]
        return o

    def toggle_simulation(self) -> bool:
        self.simulation_active = not self.simulation_active
        if self.simulation_active:
            self.sim_start_time = time.time()
        return self.simulation_active

    def reset_simulation(self) -> str:
        self.sim_start_time = time.time()
        self.active_trackers.clear()
        self._recent_events.clear()
        self.drone.spawn_random()
        return self.drone.id

    def toggle_auto_tracking(self) -> bool:
        self.auto_tracking_enabled = not self.auto_tracking_enabled
        return self.auto_tracking_enabled

    def get_burst_generation(self, node_id: int) -> int:
        gen = self._burst_generations.get(node_id, 0) + 1
        self._burst_generations[node_id] = gen
        return gen

    def is_current_burst_generation(self, node_id: int, gen: int) -> bool:
        return self._burst_generations.get(node_id) == gen

    async def calculation_loop(self):
        last_loop_time = time.time()

        while True:
            await asyncio.sleep(0.5)
            now = time.time()
            dt = min(1.0, max(0.1, now - last_loop_time))
            last_loop_time = now

            if self.simulation_active:
                self.drone.step(dt)

            payload = {
                "tracks": [],
                "ew_nodes": [],
                "zones": [],
                "sensors": [],
                "active_events": [],
                "timestamp": now,
                "simulation_active": self.simulation_active,
                "auto_tracking": self.auto_tracking_enabled,
                "emergency_override": False,
                "threat_info": None,
                "emergency_112_alert": None,
                "recent_downed": [],
                "total_downed_count": 0
            }

            self._recent_events = [ev for ev in self._recent_events if now - ev.get("time", 0) < 18.0]
            payload["active_events"] = self._recent_events

            async with async_session() as session:
                db_dirty = False

                # 1. Завантаження тактичних зон
                q_zones = await session.execute(select(TacticalZoneModel))
                db_zones = q_zones.scalars().all()
                zone_fp = tuple((z.id, z.zone_type, z.coordinates) for z in db_zones)
                if self._zone_cache["fp"] != zone_fp:
                    safe_shapely, caution_shapely, danger_shapely, items = [], [], [], []
                    for z in db_zones:
                        coords = json.loads(z.coordinates)
                        enu_points = [latlon_to_enu(p[0], p[1])[:2] for p in coords]
                        try:
                            poly = Polygon(enu_points)
                            if not poly.is_valid:
                                poly = poly.buffer(0)
                        except Exception:
                            continue
                        items.append((poly, z.name, z.zone_type))
                        if z.zone_type == "safe":
                            safe_shapely.append(poly)
                        elif z.zone_type == "caution":
                            caution_shapely.append(poly)
                        else:
                            danger_shapely.append(poly)

                    self._zone_cache = {
                        "fp": zone_fp,
                        "safe": safe_shapely,
                        "caution": caution_shapely,
                        "danger": danger_shapely,
                        "items": items
                    }

                safe_shapely = self._zone_cache["safe"]
                caution_shapely = self._zone_cache["caution"]
                danger_shapely = self._zone_cache["danger"]

                for z in db_zones:
                    payload["zones"].append({
                        "id": z.id,
                        "name": z.name,
                        "zone_type": z.zone_type,
                        "coordinates": json.loads(z.coordinates)
                    })

                # 2. Сенсори та критичні активи (ОКІ)
                q_sensors = await session.execute(select(TacticalSensorModel))
                db_sensors = q_sensors.scalars().all()

                ci_assets = []
                for s in db_sensors:
                    payload["sensors"].append({
                        "id": s.id,
                        "name": s.name,
                        "sensor_type": s.sensor_type,
                        "lat": s.lat,
                        "lon": s.lon,
                        "detection_radius": s.detection_radius,
                        "description": s.description
                    })
                    if s.sensor_type == "target_asset":
                        cx, cy, _ = latlon_to_enu(s.lat, s.lon, s.alt)
                        ci_assets.append({
                            "id": s.id,
                            "name": s.name,
                            "x": cx,
                            "y": cy,
                            "radius": s.detection_radius
                        })

                # 3. Виявлення сенсорами відповідно до специфіки БПЛА
                cur_lat, cur_lon, cur_alt = enu_to_latlon(self.drone.x, self.drone.y, self.drone.z)
                drone_detected_this_frame = False
                detected_by_name = None
                detected_type = None
                detection_note = ""

                for s in db_sensors:
                    if s.sensor_type == "target_asset":
                        continue
                    sx, sy, _ = latlon_to_enu(s.lat, s.lon, s.alt)
                    dist_2d = math.hypot(self.drone.x - sx, self.drone.y - sy)

                    # Розрахунок ефективного радіусу під фізику конкретного дрона
                    if s.sensor_type == "camera":
                        # Оптична камера: залежить від оптичної помітності БПЛА
                        effective_r = s.detection_radius * self.drone.optical_visibility
                        if dist_2d <= effective_r and self.drone.z <= 1200.0:
                            drone_detected_this_frame = True
                            detected_by_name = s.name
                            detected_type = "camera"
                            detection_note = f"Оптична фіксація силуету {self.drone.drone_type} камерою ({int(dist_2d)}м)"
                            break

                    elif s.sensor_type == "acoustic":
                        # Акустичний датчик: сильно залежить від шуму мотора
                        effective_r = s.detection_radius * self.drone.acoustic_loudness
                        if self.drone.z > 800.0:
                            effective_r *= (800.0 / self.drone.z)
                        if dist_2d <= effective_r:
                            drone_detected_this_frame = True
                            detected_by_name = s.name
                            detected_type = "acoustic"
                            detection_note = f"Спектр ДВЗ {self.drone.drone_type} мікрофоном ({int(dist_2d)}м)"
                            break

                    elif s.sensor_type in ("rf_24ghz", "rf_detector"):
                        # RF-датчик: фіксує ТІЛЬКИ дрони з активним радіоканалом!
                        if self.drone.rf_emission and dist_2d <= s.detection_radius:
                            drone_detected_this_frame = True
                            detected_by_name = s.name
                            detected_type = "rf_24ghz"
                            detection_note = f"Радіоперехоплення телеметрії 2.4 ГГц {self.drone.drone_type} ({int(dist_2d)}м)"
                            break

                    elif s.sensor_type == "observation_post":
                        # МВГ / Спостережний пост
                        effective_r = s.detection_radius * self.drone.optical_visibility
                        if dist_2d <= effective_r:
                            drone_detected_this_frame = True
                            detected_by_name = s.name
                            detected_type = "observation_post"
                            detection_note = f"Візуальний контакт МВГ за азимутом ({int(dist_2d)}м)"
                            break

                # 4. Дзвінки 112 (СУВОРО В НАСЕЛЕНИХ ПУНКТАХ + РАНДОМНИЙ EVENT)
                # Перевіряємо, чи дрон пролітає над одним із населених пунктів
                nearest_hub = None
                min_hub_dist = float('inf')
                for hub in self._hub_enu_cache:
                    h_dist = math.hypot(self.drone.x - hub["x"], self.drone.y - hub["y"])
                    if h_dist < min_hub_dist:
                        min_hub_dist = h_dist
                        nearest_hub = hub

                # Дзвінок можливий ТІЛЬКИ над населеним пунктом (радіус <= 2500 м)
                if nearest_hub and min_hub_dist <= 2500.0 and (now - self.drone.last_112_time > 8.0):
                    # Шанс дзвінка залежить від гучності шуму двигуна БПЛА
                    call_chance = 0.22 * self.drone.acoustic_loudness
                    if random.random() < call_chance:
                        self.drone.last_112_time = now
                        drone_detected_this_frame = True
                        detected_by_name = f"Дзвінок 112 ({nearest_hub['name']})"
                        detected_type = "witness_report"

                        # Невеликий шанс (20%) на детальне розпізнавання силуету
                        detailed_witness = random.random() < 0.20
                        if detailed_witness:
                            detection_note = f"Очевидець ({nearest_hub['name']}): візуально спостерігає силует {self.drone.drone_type}"
                            call_msg = f"Очевидець візуально бачить дельта-крило {self.drone.drone_type}"
                        else:
                            detection_note = f"Очевидець ({nearest_hub['name']}): повідомляє про характерний гуркіт дрона (візуально не видно)"
                            call_msg = "Громадяни повідомляють про звук мопеда/ДВЗ на низькій висоті"

                        call_lat = nearest_hub["lat"] + random.uniform(-0.003, 0.003)
                        call_lon = nearest_hub["lon"] + random.uniform(-0.003, 0.003)
                        self._recent_events.append({
                            "id": int(now * 1000),
                            "type": "witness_call",
                            "title": f"СИГНАЛ 112: {nearest_hub['name'].upper()}",
                            "message": call_msg,
                            "lat": call_lat,
                            "lon": call_lon,
                            "time": now
                        })

                # Запис точки контакту в історію засічок дрона
                if drone_detected_this_frame and self.drone.status != "CRASHED":
                    if (not self.drone.detection_history) or (now - self.drone.detection_history[-1]["t"] >= 1.6):
                        noise_sigma = 8.0 if detected_type == "camera" else (20.0 if detected_type == "acoustic" else 35.0)
                        self.drone.detection_history.append({
                            "x": self.drone.x + random.gauss(0, noise_sigma),
                            "y": self.drone.y + random.gauss(0, noise_sigma),
                            "z": self.drone.z + random.gauss(0, 5.0),
                            "t": now,
                            "sensor": detected_by_name,
                            "type": detected_type,
                            "note": detection_note
                        })
                        if len(self.drone.detection_history) > 10:
                            self.drone.detection_history.pop(0)

                # 5. Двоетапне супроводження (FOG OF WAR: якщо 0 засічок — дрон не передається!)
                target_key = self.drone.id
                num_detections = len(self.drone.detection_history)
                primary_target = None

                # КРОК 1: Первинний контакт (1 засічка) — курс, швидкість і ціль НЕВІДОМІ
                if num_detections == 1 and self.drone.status != "CRASHED":
                    det = self.drone.detection_history[-1]
                    det_lat, det_lon, det_alt = enu_to_latlon(det["x"], det["y"], det["z"])

                    track_data = {
                        "id": target_key,
                        "drone_type": self.drone.drone_type,
                        "status": "DETECTING",
                        "detection_stage": "INITIAL_CONTACT",
                        "detection_count": 1,
                        "last_sensor": det["sensor"],
                        "detection_timeline": [
                            f"{datetime.fromtimestamp(det['t']).strftime('%H:%M:%S')} — 1-й контакт: {det['sensor']} ({det['note']})"
                        ],
                        "lat": det_lat,
                        "lon": det_lon,
                        "alt": det_alt,
                        "speed": None,
                        "heading": None,
                        "predicted_30s": None,
                        "predicted_60s": None,
                        "crash_point": None,
                        "crash_safety": None,
                        "impact_ellipse": None,
                        "is_safe_to_engage": False,
                        "is_ci_critical": False,
                        "ci_distance": None,
                        "nearest_ci": None,
                        "target_asset_name": "Не визначено (очікується 2-й контакт)...",
                        "raw_enu": [det["x"], det["y"], det["z"], 0.0, 0.0, 0.0]
                    }
                    payload["tracks"].append(track_data)
                    primary_target = track_data

                # КРОК 2: Другий і наступні контакти (>=2) — розрахунок кінематики, Калман, цілі та зони
                elif num_detections >= 2:
                    p1 = self.drone.detection_history[-2]
                    p2 = self.drone.detection_history[-1]
                    dt_meas = max(0.1, p2["t"] - p1["t"])
                    calc_vx = (p2["x"] - p1["x"]) / dt_meas
                    calc_vy = (p2["y"] - p1["y"]) / dt_meas
                    calc_vz = (p2["z"] - p1["z"]) / dt_meas

                    if target_key not in self.active_trackers:
                        tracker = DroneKalmanFilter(p2["x"], p2["y"], p2["z"])
                        tracker.state[3] = calc_vx
                        tracker.state[4] = calc_vy
                        tracker.state[5] = calc_vz
                        self.active_trackers[target_key] = tracker
                    else:
                        tracker = self.active_trackers[target_key]
                        tracker.predict(dt)
                        tracker.update(np.array([p2["x"], p2["y"], p2["z"]]))

                    sx, sy, sz = tracker.state[0], tracker.state[1], tracker.state[2]
                    vx, vy, vz = tracker.state[3], tracker.state[4], tracker.state[5]
                    speed = float(np.sqrt(vx**2 + vy**2 + vz**2))
                    heading = (np.degrees(np.arctan2(vx, vy)) + 360.0) % 360.0

                    t_lat, t_lon, t_alt = enu_to_latlon(sx, sy, sz)
                    p30_x, p30_y, _ = tracker.extrapolate(30.0)
                    p60_x, p60_y, _ = tracker.extrapolate(60.0)
                    lat_30, lon_30, _ = enu_to_latlon(p30_x, p30_y, sz)
                    lat_60, lon_60, _ = enu_to_latlon(p60_x, p60_y, sz)

                    predicted_target_ci, _ = InterceptionPlanner.predict_intended_target(sx, sy, vx, vy, ci_assets)
                    intended_target_display = predicted_target_ci if predicted_target_ci else self.drone.target_name

                    imp_x, imp_y, t_fall, sig_al, sig_cr, imp_hdg = InterceptionPlanner.predict_impact_ellipse(
                        sx, sy, sz, vx, vy, vz, tracker.P
                    )
                    imp_lat, imp_lon, _ = enu_to_latlon(imp_x, imp_y, 0)
                    try:
                        crash_safety = risk_safety_at_enu(
                            imp_x, imp_y, imp_lat, imp_lon, safe_shapely, caution_shapely, danger_shapely, ci_assets
                        )
                    except Exception:
                        crash_safety = 0.45

                    is_safe = crash_safety >= 0.60

                    ellipse_pts = []
                    try:
                        for _k in range(12):
                            _a = 2.0 * math.pi * _k / 12.0
                            _ex = 2.0 * sig_al * math.cos(_a)
                            _ey = 2.0 * sig_cr * math.sin(_a)
                            _rx = _ex * math.cos(imp_hdg) + _ey * math.sin(imp_hdg)
                            _ry = -_ex * math.sin(imp_hdg) + _ey * math.cos(imp_hdg)
                            _elat, _elon, _ = enu_to_latlon(imp_x + _rx, imp_y + _ry, 0)
                            ellipse_pts.append([_elat, _elon])
                    except Exception:
                        ellipse_pts = []

                    # Перевірка критичної близькості до ОКІ (<= 2500 м)
                    is_ci_critical, min_dist_ci, nearest_ci_name = InterceptionPlanner.evaluate_ci_proximity(
                        sx, sy, ci_assets, threshold_m=2500.0
                    )

                    timeline = []
                    for d_item in self.drone.detection_history[-3:]:
                        t_str = datetime.fromtimestamp(d_item["t"]).strftime("%H:%M:%S")
                        timeline.append(f"{t_str} — {d_item['sensor']}: {d_item['note']}")

                    dist_between_last = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                    calc_note = f"ΔS={dist_between_last:.0f}м за {dt_meas:.1f}с -> V={(speed*3.6):.0f} км/год | Курс {heading:.0f}°"

                    track_data = {
                        "id": target_key,
                        "drone_type": self.drone.drone_type,
                        "status": self.drone.status,
                        "detection_stage": "TRACKED",
                        "detection_count": num_detections,
                        "last_sensor": p2["sensor"],
                        "detection_timeline": timeline,
                        "kinematics_note": calc_note,
                        "lat": t_lat,
                        "lon": t_lon,
                        "alt": max(0.0, t_alt),
                        "speed": speed if self.drone.status != "CRASHED" else 0.0,
                        "heading": heading,
                        "predicted_30s": [lat_30, lon_30] if self.drone.status != "CRASHED" else [t_lat, t_lon],
                        "predicted_60s": [lat_60, lon_60] if self.drone.status != "CRASHED" else [t_lat, t_lon],
                        "crash_point": [imp_lat, imp_lon],
                        "crash_safety": round(crash_safety * 100.0, 1),
                        "impact_ellipse": ellipse_pts,
                        "is_safe_to_engage": is_safe if self.drone.status == "CRUISING" else False,
                        "is_ci_critical": is_ci_critical if self.drone.status == "CRUISING" else False,
                        "ci_distance": round(min_dist_ci, 0) if (nearest_ci_name and math.isfinite(min_dist_ci)) else None,
                        "nearest_ci": nearest_ci_name,
                        "target_asset_name": intended_target_display,
                        "raw_enu": [sx, sy, sz, vx, vy, vz]
                    }
                    payload["tracks"].append(track_data)
                    primary_target = track_data

                # 6. Фіксація збиття та ВИКЛИК 112 / ДСНС при падінні у червону/помаранчеву зону
                if self.drone.status == "CRASHED" and not self.drone.downed_saved:
                    c_lat, c_lon, _ = enu_to_latlon(self.drone.x, self.drone.y, 0.0)
                    pt = Point(self.drone.x, self.drone.y)
                    crash_zone_name = "Відкрита місцевість"
                    crash_zone_type = "safe"

                    for poly, zname, ztype in self._zone_cache["items"]:
                        try:
                            if poly.contains(pt):
                                prefix = '🟢 ' if ztype == 'safe' else ('🟡 ' if ztype == 'caution' else '🔴 ')
                                crash_zone_name = f"{prefix}{zname}"
                                crash_zone_type = ztype
                                break
                        except Exception:
                            continue

                    # Розрахунок радіуса розльоту уламків
                    debris_radius = round(self.drone.base_debris_radius + random.uniform(15.0, 45.0), 1)
                    self.drone.actual_debris_radius = debris_radius

                    # ПРАВИЛО: Якщо впав у червону чи помаранчеву зону — викликаємо 112/ДСНС
                    called_112 = False
                    emergency_note = "Утилізовано в Killbox (зелена зона). Загрози цивільній забудові немає."

                    if crash_zone_type in ("danger", "caution"):
                        called_112 = True
                        zone_label = "ЧЕРВОНІЙ ЗОНІ (житлова забудова)" if crash_zone_type == "danger" else "ПОМАРАНЧЕВІЙ БУФЕРНІЙ ЗОНІ"
                        emergency_note = (
                            f"🚨 ВИКЛИК 112 / ДСНС: Уламки {self.drone.drone_type} впали у {zone_label}!\n"
                            f"Точка: {c_lat:.5f}°, {c_lon:.5f}°. Розліт уламків ~{debris_radius}м. "
                            f"Направлено пожежно-рятувальні підрозділи ДСНС та МОЗ!"
                        )

                        self._recent_events.append({
                            "id": int(now * 1000),
                            "type": "emergency_112_call",
                            "title": "СЛУЖБА 112 / ДСНС: ПАДІННЯ УЛАМКІВ БПЛА",
                            "message": emergency_note,
                            "lat": c_lat,
                            "lon": c_lon,
                            "time": now
                        })

                        payload["emergency_112_alert"] = {
                            "called": True,
                            "message": emergency_note,
                            "lat": c_lat,
                            "lon": c_lon,
                            "radius": debris_radius,
                            "drone_type": self.drone.drone_type
                        }

                    downed_record = DownedDroneModel(
                        drone_id=self.drone.id,
                        drone_type=self.drone.drone_type,
                        spawn_time=self.drone.spawn_time,
                        downed_time=datetime.now(),
                        spawn_lat=self.drone.spawn_lat,
                        spawn_lon=self.drone.spawn_lon,
                        target_name=self.drone.target_name,
                        interceptor_name=self.drone.interceptor_name,
                        crash_lat=c_lat,
                        crash_lon=c_lon,
                        crash_zone=crash_zone_name,
                        debris_radius_m=debris_radius,
                        emergency_112_called=called_112,
                        emergency_details=emergency_note,
                        status="CRASHED"
                    )
                    session.add(downed_record)
                    db_dirty = True
                    self.drone.downed_saved = True

                # 7. Супроводження та бойова робота РЕБ
                q_nodes = await session.execute(select(EWNodeModel))
                db_nodes = q_nodes.scalars().all()

                best_interceptor_id = None
                min_ew_dist = float('inf')

                for node in db_nodes:
                    node_x, node_y, node_z = latlon_to_enu(node.lat, node.lon, node.alt)
                    distance = float('inf')
                    target_azimuth = node.current_azimuth
                    elevation = 0.0
                    lead_x = lead_y = lead_z = None
                    has_lead = False

                    if primary_target and primary_target.get("detection_stage") == "TRACKED" and self.auto_tracking_enabled:
                        sx, sy, sz, vx, vy, vz = primary_target["raw_enu"]
                        lead_x, lead_y, lead_z = InterceptionPlanner.predict_lead_point(sx, sy, sz, vx, vy, vz, lead_time_sec=2.0)
                        has_lead = True
                        target_azimuth, elevation, distance = calculate_azimuth_elevation(node_x, node_y, node_z, lead_x, lead_y, lead_z)

                        if distance <= node.max_range:
                            prev_az = node.current_azimuth
                            az_diff = ((target_azimuth - prev_az + 180.0) % 360.0) - 180.0
                            adaptive_beam = InterceptionPlanner.calculate_adaptive_beamwidth(distance, node.max_range)
                            if abs(round(target_azimuth, 1) - prev_az) > 1e-9 or abs(adaptive_beam - node.beamwidth) > 1e-9:
                                node.current_azimuth = round(target_azimuth, 1)
                                node.beamwidth = adaptive_beam
                                db_dirty = True

                            if distance < min_ew_dist:
                                min_ew_dist = distance
                                best_interceptor_id = node.id

                            _pelco_cmd = PelcoDController.build_pan_tilt_command(
                                address=node.id,
                                pan_speed=int(min(63, max(10, abs(vx) * 0.8))),
                                tilt_speed=20,
                                left=(az_diff < 0.0),
                                up=(elevation > 15.0)
                            )
                            logger.debug("pelco node=%s az=%.1f el=%.1f", node.id, target_azimuth, elevation)

                    # ЛОГІКА ЗБИТТЯ:
                    if primary_target and primary_target.get("status") == "CRUISING" and primary_target.get("detection_stage") == "TRACKED":
                        want_tx = False

                        # 1. ПРАВИЛО: Екстрений захист критичного об'єкта (в будь-якій зоні)
                        if primary_target["is_ci_critical"] and node.id == best_interceptor_id and node.is_armed:
                            want_tx = True
                            payload["emergency_override"] = True
                            payload["threat_info"] = f"🚨 ЕКСТРЕНИЙ ЗАХИСТ ОКІ: {primary_target['nearest_ci']} ({primary_target['ci_distance']}м) — збиття у будь-якій зоні!"

                        # 2. ПРАВИЛО: Збиття над зеленою (Killbox) або помаранчевою (буферною) зоною
                        elif self.auto_tracking_enabled and primary_target["is_safe_to_engage"] and node.id == best_interceptor_id and node.is_armed:
                            want_tx = True
                            payload["threat_info"] = f"🎯 ХІРУРГІЧНЕ ПРИДУШЕННЯ: {node.name} глушить {self.drone.drone_type} над зеленою зоною"

                        if node.is_transmitting != want_tx and want_tx:
                            node.is_transmitting = True
                            db_dirty = True
                        elif node.is_transmitting != want_tx and not want_tx and not node.is_armed:
                            node.is_transmitting = False
                            db_dirty = True

                    if primary_target and primary_target.get("status") == "CRASHED":
                        if node.is_transmitting:
                            node.is_transmitting = False
                            db_dirty = True

                    if node.is_transmitting and primary_target and primary_target.get("status") == "CRUISING":
                        angle_diff = abs((target_azimuth - node.current_azimuth + 180.0) % 360.0 - 180.0)
                        if distance <= node.max_range and angle_diff <= (node.beamwidth / 2.0 + 4.0):
                            self.drone.apply_jamming(node.name)
                            payload["threat_info"] = f"⚡ ВЛУЧАННЯ РЕБ: {node.name} зірвав наведення {self.drone.id} ({self.drone.drone_type})!"

                    lead_coord = None
                    if (has_lead and lead_x is not None and lead_y is not None and lead_z is not None
                            and primary_target and primary_target.get("status") != "CRASHED"
                            and self.auto_tracking_enabled and distance <= node.max_range):
                        lead_coord = enu_to_latlon(lead_x, lead_y, lead_z)[:2]

                    payload["ew_nodes"].append({
                        "id": node.id,
                        "name": node.name,
                        "lat": node.lat,
                        "lon": node.lon,
                        "azimuth": node.current_azimuth,
                        "beamwidth": node.beamwidth,
                        "max_range": node.max_range,
                        "is_armed": node.is_armed,
                        "is_transmitting": node.is_transmitting,
                        "target_lead_coord": lead_coord
                    })

                # 8. Останні збиті дрони
                q_downed = await session.execute(
                    select(DownedDroneModel).order_by(desc(DownedDroneModel.id)).limit(5)
                )
                recent_list = q_downed.scalars().all()
                for row in recent_list:
                    payload["recent_downed"].append({
                        "id": row.id,
                        "drone_id": row.drone_id,
                        "drone_type": getattr(row, "drone_type", "Shahed-136 (Герань-2)"),
                        "spawn_time": row.spawn_time.strftime("%d.%m.%Y %H:%M:%S") if row.spawn_time else "-",
                        "downed_time": row.downed_time.strftime("%d.%m.%Y %H:%M:%S") if row.downed_time else "-",
                        "spawn_coords": f"{row.spawn_lat:.4f}°, {row.spawn_lon:.4f}°",
                        "target_name": row.target_name,
                        "interceptor_name": row.interceptor_name,
                        "crash_coords": f"{row.crash_lat:.4f}°, {row.crash_lon:.4f}°",
                        "crash_zone": row.crash_zone,
                        "debris_radius_m": getattr(row, "debris_radius_m", 120.0),
                        "emergency_112_called": getattr(row, "emergency_112_called", False),
                        "emergency_details": getattr(row, "emergency_details", ""),
                        "status": row.status
                    })

                count_res = await session.execute(select(func.count()).select_from(DownedDroneModel))
                payload["total_downed_count"] = int(count_res.scalar() or 0)

                if db_dirty:
                    await session.commit()
                else:
                    await session.rollback()

            await ws_manager.broadcast_json(self.sanitize(payload))

c2_engine = C2Engine()
import asyncio
import json
import time
import math
import random
from datetime import datetime
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import Point, Polygon
from sqlalchemy import select, delete, desc, func
import logging
import numpy as np

from app.config import settings
from app.database import init_db, async_session
from app.models import EWNodeModel, TacticalZoneModel, TacticalSensorModel, DownedDroneModel
from app.schemas import (
    DetectionCreate, ArmEWCommand, EWNodeCreate, EWNodeUpdate,
    TacticalZoneCreate, TacticalZoneUpdate,
    TacticalSensorCreate, TacticalSensorUpdate
)
from app.core.geo import latlon_to_enu, enu_to_latlon, calculate_azimuth_elevation
from app.core.kalman import DroneKalmanFilter
from app.core.planner import InterceptionPlanner
from app.core.risk_h3 import (
    load_grid as risk_load_grid,
    safety_at_enu as risk_safety_at_enu,
    grid_for_frontend as risk_grid_cells,
    generate_district_zones_from_h3
)
from app.hardware.pelco import PelcoDController
from app.seed.ew_optimizer import auto_optimize_and_apply_ew


logger = logging.getLogger(__name__)


class DroneSimulation:
    """
    Фізична модель польоту ворожого БПЛА (Shahed-136).
    Дрон з'являється глибоко за межами міста (18-26 км),
    вибирає стратегічну ціль і прямує до неї на висоті 160-240м.
    Поки жоден сенсор або свідок його не засік — він залишається невидимим для C2.
    """
    def __init__(self):
        self.t_sim = 0.0
        self.spawn_random()

    def spawn_random(self, ci_targets: list = None):
        # Поява на рубежах 18-26 км на північ, північний схід або північний захід від Києва
        angle_deg = random.choice([
            random.uniform(-70.0, -25.0), # Північний захід (Чорнобильський / Гостомельський сектор)
            random.uniform(-25.0, 25.0),  # Північ (Київське море / Білоруський напрямок)
            random.uniform(25.0, 75.0)    # Північний схід (Чернігівський / Броварський сектор)
        ])
        dist = random.uniform(18000.0, 26000.0)
        rad = math.radians(angle_deg)

        self.x = dist * math.sin(rad)
        self.y = dist * math.cos(rad)
        self.z = random.uniform(160.0, 240.0)

        self.spawn_lat, self.spawn_lon, _ = enu_to_latlon(self.x, self.y, self.z)
        self.spawn_time = datetime.now()

        # Вибір цілі серед доступних критичних об'єктів або резервний список
        default_targets = [
            ("Київська ГЕС (Турбінний зал)", latlon_to_enu(50.5898, 30.5050)[:2]),
            ("ТЕЦ-6 (Деснянський район)", latlon_to_enu(50.5312, 30.6580)[:2]),
            ("ПС 750кВ «Північна»", latlon_to_enu(50.6200, 30.4500)[:2]),
            ("ТЕЦ-5 (Промислова Теличка)", latlon_to_enu(50.4005, 30.5645)[:2]),
            ("Дарницька ТЕЦ", latlon_to_enu(50.4350, 30.6350)[:2]),
        ]

        if ci_targets and len(ci_targets) > 0:
            chosen = random.choice(ci_targets)
            self.target_name = chosen["name"]
            tgt_x, tgt_y = chosen["x"], chosen["y"]
        else:
            chosen = random.choice(default_targets)
            self.target_name = chosen[0]
            tgt_x, tgt_y = chosen[1]

        # Невелике тактичне розсіювання точки прицілювання
        tgt_x += random.uniform(-250.0, 250.0)
        tgt_y += random.uniform(-250.0, 250.0)

        dx = tgt_x - self.x
        dy = tgt_y - self.y
        dist_to_tgt = math.hypot(dx, dy)

        speed = random.uniform(49.0, 54.0) # ~175-195 км/год (характерний круїз Shahed-136)
        self.vx = (dx / dist_to_tgt) * speed
        self.vy = (dy / dist_to_tgt) * speed
        self.vz = 0.0

        self.status = "CRUISING"
        self.id = f"SHAHED-{random.randint(102, 989)}"
        self.crashed_timer = 0.0
        self.interceptor_name = "Невідомо"
        self.downed_saved = False

        # Хронологія сенсорних засічок: [{x, y, z, t, sensor_name, type, note}]
        self.detection_history: List[dict] = []
        self.last_112_time = 0.0
        self.last_sensor_time = 0.0

    def apply_jamming(self, interceptor_name: str):
        if self.status == "CRUISING":
            self.status = "JAMMED"
            self.interceptor_name = interceptor_name
            self.vz = -random.uniform(20.0, 25.0)

    _DRAG_TAU = 2.8

    def step(self, dt: float):
        if self.status == "CRASHED":
            self.crashed_timer += dt
            if self.crashed_timer >= 5.0:
                self.spawn_random()
            return

        if self.status == "JAMMED":
            decay = math.exp(-dt / self._DRAG_TAU)
            self.vx *= decay
            self.vy *= decay
            self.x += (self.vx + settings.WIND_VECTOR_X) * dt
            self.y += (self.vy + settings.WIND_VECTOR_Y) * dt
            self.z += self.vz * dt

            if self.z <= 0.0:
                self.z = 0.0
                self.vx = 0.0
                self.vy = 0.0
                self.vz = 0.0
                self.status = "CRASHED"
                self.crashed_timer = 0.0
            return

        self.t_sim += dt
        turb_x = math.sin(self.t_sim / 4.0) * 0.3
        turb_y = math.cos(self.t_sim / 4.0) * 0.3
        self.x += (self.vx + turb_x) * dt
        self.y += (self.vy + turb_y) * dt

        if math.hypot(self.x, self.y) > 50000:
            self.spawn_random()


simulated_drone = DroneSimulation()
active_trackers: Dict[str, DroneKalmanFilter] = {}
active_connections: list[WebSocket] = []

simulation_active = True
sim_start_time = time.time()
auto_tracking_enabled = True

_zone_cache: Dict = {"fp": None, "safe": [], "caution": [], "danger": [], "items": []}
_burst_generations: Dict[int, int] = {}
_recent_events: List[dict] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        ok = risk_load_grid()
        logger.info("risk_h3 grid loaded=%s", ok)
    except Exception as e:
        logger.warning("risk_h3 load failed: %s", e)

    # 1. Автоматичний запуск ешелонованої оптимізації РЕБ при старті
    try:
        logger.info("Запуск первинної оптимізації розташування РЕБ...")
        await auto_optimize_and_apply_ew(node_count=7, replace_existing=False)
    except Exception as e:
        logger.error("Помилка автоматичної оптимізації РЕБ при старті: %s", e)

    # 2. Запуск циклу супроводу C2
    bg_task = asyncio.create_task(c2_calculation_loop())
    yield
    bg_task.cancel()


app = FastAPI(title="Surgical EW Control System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def c2_calculation_loop():
    global sim_start_time, auto_tracking_enabled, simulated_drone, active_trackers, _recent_events
    last_loop_time = time.time()

    while True:
        await asyncio.sleep(0.5)
        now = time.time()
        dt = min(1.0, max(0.1, now - last_loop_time))
        last_loop_time = now

        if simulation_active:
            simulated_drone.step(dt)

        payload = {
            "tracks": [],
            "ew_nodes": [],
            "zones": [],
            "sensors": [],
            "active_events": [],
            "timestamp": now,
            "simulation_active": simulation_active,
            "auto_tracking": auto_tracking_enabled,
            "emergency_override": False,
            "threat_info": None,
            "recent_downed": [],
            "total_downed_count": 0
        }

        # Очищення старих сповіщень 112 старших 15 секунд
        _recent_events = [ev for ev in _recent_events if now - ev.get("time", 0) < 15.0]
        payload["active_events"] = _recent_events

        async with async_session() as session:
            db_dirty = False

            # 1. Завантаження тактичних зон
            q_zones = await session.execute(select(TacticalZoneModel))
            db_zones = q_zones.scalars().all()
            zone_fp = tuple((z.id, z.zone_type, z.coordinates) for z in db_zones)
            if _zone_cache["fp"] != zone_fp:
                safe_shapely = []
                caution_shapely = []
                danger_shapely = []
                items = []
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

                _zone_cache["fp"] = zone_fp
                _zone_cache["safe"] = safe_shapely
                _zone_cache["caution"] = caution_shapely
                _zone_cache["danger"] = danger_shapely
                _zone_cache["items"] = items
            else:
                safe_shapely = _zone_cache["safe"]
                caution_shapely = _zone_cache["caution"]
                danger_shapely = _zone_cache["danger"]

            for z in db_zones:
                payload["zones"].append({
                    "id": z.id,
                    "name": z.name,
                    "zone_type": z.zone_type,
                    "coordinates": json.loads(z.coordinates)
                })

            # 2. Сенсори та критичні активи
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
                    ci_x, ci_y, _ = latlon_to_enu(s.lat, s.lon, s.alt)
                    ci_assets.append({"name": s.name, "x": ci_x, "y": ci_y, "lat": s.lat, "lon": s.lon})

            # 3. Сенсорне перекриття та генерація виявлення (Detection Logic)
            cur_lat, cur_lon, cur_alt = enu_to_latlon(simulated_drone.x, simulated_drone.y, simulated_drone.z)
            drone_detected_this_frame = False
            detected_by_name = None
            detected_type = None
            detection_note = ""

            # А. Перевірка засікання встановленими сенсорами
            for s in db_sensors:
                if s.sensor_type == "target_asset":
                    continue
                sx, sy, _ = latlon_to_enu(s.lat, s.lon, s.alt)
                dist_sensor = math.hypot(simulated_drone.x - sx, simulated_drone.y - sy)
                if dist_sensor <= s.detection_radius:
                    drone_detected_this_frame = True
                    detected_by_name = s.name
                    detected_type = s.sensor_type
                    if s.sensor_type == "camera":
                        detection_note = f"Фотофіксація БПЛА оптичною камерою ({int(dist_sensor)}м)"
                    elif s.sensor_type == "acoustic":
                        detection_note = f"Акустичний спектр ДВЗ зафіксовано датчиком ({int(dist_sensor)}м)"
                    elif s.sensor_type == "observation_post":
                        detection_note = f"Візуальний контакт МВГ за азимутом ({int(dist_sensor)}м)"
                    break

            # Б. Моделювання випадкових дзвінків 112 (залежно від щільності населення)
            current_safety = risk_safety_at_enu(
                simulated_drone.x, simulated_drone.y, cur_lat, cur_lon,
                safe_shapely, caution_shapely, danger_shapely, ci_assets
            )
            # Чим нижчий safety (червона зона/густа забудова), тим вища щільність населення
            pop_density = max(0.0, min(1.0, 1.0 - current_safety))

            # Дзвінок 112 виникає лише якщо дрон летить над населеною зоною
            if pop_density > 0.35 and (now - simulated_drone.last_112_time > 7.0):
                # Ймовірність дзвінка різко зростає над містом
                call_chance = (pop_density - 0.30) * 0.65
                if random.random() < call_chance:
                    simulated_drone.last_112_time = now
                    drone_detected_this_frame = True
                    district_label = "Спальний район міста" if pop_density > 0.6 else "Приміська забудова"
                    detected_by_name = f"Дзвінок 112 ({district_label})"
                    detected_type = "witness_report"
                    detection_note = f"Громадяни повідомляють про звук низьковисотного БПЛА (щільність {int(pop_density*100)}%)"

                    call_lat = cur_lat + random.uniform(-0.003, 0.003)
                    call_lon = cur_lon + random.uniform(-0.003, 0.003)
                    _recent_events.append({
                        "id": int(now * 1000),
                        "type": "witness_call",
                        "title": f"СИГНАЛ 112: ЗВУК ДВИГУНА БПЛА",
                        "message": f"Очевидці ({district_label}) чують характерний гуркіт дрона",
                        "lat": call_lat,
                        "lon": call_lon,
                        "time": now
                    })

            # Якщо є засікання — додаємо в історію детекцій БПЛА (не частіше ніж раз на 1.8 с)
            if drone_detected_this_frame and simulated_drone.status != "CRASHED":
                if (not simulated_drone.detection_history) or (now - simulated_drone.detection_history[-1]["t"] >= 1.8):
                    noise_sigma = 8.0 if detected_type == "camera" else (22.0 if detected_type == "acoustic" else 40.0)
                    simulated_drone.detection_history.append({
                        "x": simulated_drone.x + random.gauss(0, noise_sigma),
                        "y": simulated_drone.y + random.gauss(0, noise_sigma),
                        "z": simulated_drone.z + random.gauss(0, 4.0),
                        "t": now,
                        "sensor": detected_by_name,
                        "type": detected_type,
                        "note": detection_note
                    })
                    if len(simulated_drone.detection_history) > 10:
                        simulated_drone.detection_history.pop(0)

            # 4. Аналітичне двоетапне оцінювання треку
            target_key = simulated_drone.id
            num_detections = len(simulated_drone.detection_history)
            primary_target = None

            # СТАДІЯ 0: Дрон ще не засічено жодним сенсором -> payload tracks порожній!
            if num_detections == 0:
                pass

            # СТАДІЯ 1: Первинний контакт (1 засічка)
            elif num_detections == 1:
                det = simulated_drone.detection_history[-1]
                det_lat, det_lon, det_alt = enu_to_latlon(det["x"], det["y"], det["z"])

                track_data = {
                    "id": target_key,
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
                    "speed": None,          # Невідомо
                    "heading": None,        # Невідомо
                    "predicted_30s": None,
                    "predicted_60s": None,
                    "crash_point": None,
                    "crash_safety": None,
                    "corridor_safety": None,
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

            # СТАДІЯ 2: Розрахунок швидкості та вектора за двома точками
            elif num_detections >= 2:
                p1 = simulated_drone.detection_history[-2]
                p2 = simulated_drone.detection_history[-1]
                dt_meas = max(0.1, p2["t"] - p1["t"])
                calc_vx = (p2["x"] - p1["x"]) / dt_meas
                calc_vy = (p2["y"] - p1["y"]) / dt_meas
                calc_vz = (p2["z"] - p1["z"]) / dt_meas

                if target_key not in active_trackers:
                    tracker = DroneKalmanFilter(p2["x"], p2["y"], p2["z"])
                    tracker.state[3] = calc_vx
                    tracker.state[4] = calc_vy
                    tracker.state[5] = calc_vz
                    active_trackers[target_key] = tracker
                else:
                    tracker = active_trackers[target_key]
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

                # Прогнозування ймовірної цілі за вектором руху
                predicted_target_ci, _ = InterceptionPlanner.predict_intended_target(sx, sy, vx, vy, ci_assets)
                intended_target_display = predicted_target_ci if predicted_target_ci else simulated_drone.target_name

                # Розрахунок еліпса падіння
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

                is_ci_critical, min_dist_ci, nearest_ci_name = InterceptionPlanner.evaluate_ci_proximity(
                    sx, sy, ci_assets, threshold_m=2500.0
                )

                # Формування хронології засічок для HUD
                timeline = []
                for d_item in simulated_drone.detection_history[-3:]:
                    t_str = datetime.fromtimestamp(d_item["t"]).strftime("%H:%M:%S")
                    timeline.append(f"{t_str} — {d_item['sensor']}: {d_item['note']}")

                dist_between_last = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                calc_note = f"ΔS = {dist_between_last:.0f}м за {dt_meas:.1f}с -> V = {(speed*3.6):.0f} км/год"

                track_data = {
                    "id": target_key,
                    "status": simulated_drone.status,
                    "detection_stage": "TRACKED",
                    "detection_count": num_detections,
                    "last_sensor": p2["sensor"],
                    "detection_timeline": timeline,
                    "kinematics_note": calc_note,
                    "lat": t_lat,
                    "lon": t_lon,
                    "alt": max(0.0, t_alt),
                    "speed": speed if simulated_drone.status != "CRASHED" else 0.0,
                    "heading": heading,
                    "predicted_30s": [lat_30, lon_30] if simulated_drone.status != "CRASHED" else [t_lat, t_lon],
                    "predicted_60s": [lat_60, lon_60] if simulated_drone.status != "CRASHED" else [t_lat, t_lon],
                    "crash_point": [imp_lat, imp_lon],
                    "crash_safety": round(crash_safety * 100.0, 1),
                    "impact_ellipse": ellipse_pts,
                    "is_safe_to_engage": is_safe if simulated_drone.status == "CRUISING" else False,
                    "is_ci_critical": is_ci_critical if simulated_drone.status == "CRUISING" else False,
                    "ci_distance": round(min_dist_ci, 0) if (nearest_ci_name and math.isfinite(min_dist_ci)) else None,
                    "nearest_ci": nearest_ci_name,
                    "target_asset_name": intended_target_display,
                    "raw_enu": [sx, sy, sz, vx, vy, vz]
                }
                payload["tracks"].append(track_data)
                primary_target = track_data

            elif num_detections >= 2:
                # --- СТАДІЯ 2: Розрахунок швидкості та вектора за серією детекцій ---
                # Використовуємо 2 останні засічки: v = dist / delta_t
                p1 = simulated_drone.detection_history[-2]
                p2 = simulated_drone.detection_history[-1]
                dt_meas = max(0.1, p2["t"] - p1["t"])
                calc_vx = (p2["x"] - p1["x"]) / dt_meas
                calc_vy = (p2["y"] - p1["y"]) / dt_meas
                calc_vz = (p2["z"] - p1["z"]) / dt_meas

                # Оновлення або ініціалізація фільтра Калмана
                if target_key not in active_trackers:
                    tracker = DroneKalmanFilter(p2["x"], p2["y"], p2["z"])
                    tracker.state[3] = calc_vx
                    tracker.state[4] = calc_vy
                    tracker.state[5] = calc_vz
                    active_trackers[target_key] = tracker
                else:
                    tracker = active_trackers[target_key]
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

                ellipse_pts: list = []
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

                try:
                    _samples = [(sx, sy), (p30_x, p30_y), (p60_x, p60_y), (imp_x, imp_y)]
                    _vals = []
                    for _px, _py in _samples:
                        _slat, _slon, _ = enu_to_latlon(_px, _py, 0)
                        _vals.append(risk_safety_at_enu(_px, _py, _slat, _slon, safe_shapely, caution_shapely, danger_shapely, ci_assets))
                    corridor_safety = float(sum(_vals) / len(_vals))
                except Exception:
                    corridor_safety = crash_safety

                is_ci_critical, min_dist_ci, nearest_ci_name = InterceptionPlanner.evaluate_ci_proximity(
                    sx, sy, ci_assets, threshold_m=2500.0
                )

                track_data = {
                    "id": target_key,
                    "status": simulated_drone.status,
                    "detection_stage": "TRACKED",
                    "detection_count": num_detections,
                    "last_sensor": p2["sensor"],
                    "lat": t_lat,
                    "lon": t_lon,
                    "alt": max(0.0, t_alt),
                    "speed": speed if simulated_drone.status != "CRASHED" else 0.0,
                    "heading": heading,
                    "predicted_30s": [lat_30, lon_30] if simulated_drone.status != "CRASHED" else [t_lat, t_lon],
                    "predicted_60s": [lat_60, lon_60] if simulated_drone.status != "CRASHED" else [t_lat, t_lon],
                    "crash_point": [imp_lat, imp_lon],
                    "crash_safety": round(crash_safety * 100.0, 1),
                    "corridor_safety": round(corridor_safety * 100.0, 1),
                    "impact_ellipse": ellipse_pts,
                    "is_safe_to_engage": is_safe if simulated_drone.status == "CRUISING" else False,
                    "is_ci_critical": is_ci_critical if simulated_drone.status == "CRUISING" else False,
                    "ci_distance": round(min_dist_ci, 0) if (nearest_ci_name and math.isfinite(min_dist_ci)) else None,
                    "nearest_ci": nearest_ci_name,
                    "target_asset_name": simulated_drone.target_name,
                    "raw_enu": [sx, sy, sz, vx, vy, vz]
                }
                payload["tracks"].append(track_data)
                primary_target = track_data

            # 5. Фіксація збитого дрона в БД
            if simulated_drone.status == "CRASHED" and not simulated_drone.downed_saved:
                c_lat, c_lon, _ = enu_to_latlon(simulated_drone.x, simulated_drone.y, 0.0)
                pt = Point(simulated_drone.x, simulated_drone.y)
                crash_zone_name = "Відкрита місцевість"

                for poly, zname, ztype in _zone_cache["items"]:
                    try:
                        if poly.contains(pt):
                            prefix = '🟢 ' if ztype == 'safe' else ('🟡 ' if ztype == 'caution' else '🔴 ')
                            crash_zone_name = f"{prefix}{zname}"
                            break
                    except Exception:
                        continue

                downed_record = DownedDroneModel(
                    drone_id=simulated_drone.id,
                    spawn_time=simulated_drone.spawn_time,
                    downed_time=datetime.now(),
                    spawn_lat=simulated_drone.spawn_lat,
                    spawn_lon=simulated_drone.spawn_lon,
                    target_name=simulated_drone.target_name,
                    interceptor_name=simulated_drone.interceptor_name,
                    crash_lat=c_lat,
                    crash_lon=c_lon,
                    crash_zone=crash_zone_name,
                    status="CRASHED"
                )
                session.add(downed_record)
                db_dirty = True
                simulated_drone.downed_saved = True

            # 6. Супроводження та бойова робота РЕБ (тільки коли ціль супроводжується і вектор визначений)
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

                if primary_target and primary_target.get("detection_stage") == "TRACKED" and auto_tracking_enabled:
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

                # Бойове придушення
                if primary_target and primary_target.get("status") == "CRUISING" and primary_target.get("detection_stage") == "TRACKED":
                    want_tx = False
                    if primary_target["is_ci_critical"] and node.id == best_interceptor_id and node.is_armed:
                        want_tx = True
                        payload["emergency_override"] = True
                        payload["threat_info"] = f"CRITICAL ASSET DEFENSE: Захист {primary_target['nearest_ci']} ({primary_target['ci_distance']}м)"
                    elif auto_tracking_enabled and primary_target["is_safe_to_engage"] and node.id == best_interceptor_id and node.is_armed:
                        want_tx = True
                        payload["threat_info"] = f"SURGICAL INTERCEPTION: {node.name} глушить ціль над безпечною зоною"

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
                        simulated_drone.apply_jamming(node.name)
                        payload["threat_info"] = f"⚡ ВЛУЧАННЯ РЕБ: {node.name} зірвав наведення {simulated_drone.id}!"

                lead_coord = None
                if (has_lead and lead_x is not None and lead_y is not None and lead_z is not None
                        and primary_target and primary_target.get("status") != "CRASHED"
                        and auto_tracking_enabled and distance <= node.max_range):
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

            # 7. Останні збиті дрони
            q_downed = await session.execute(
                select(DownedDroneModel).order_by(desc(DownedDroneModel.id)).limit(5)
            )
            recent_list = q_downed.scalars().all()
            for row in recent_list:
                payload["recent_downed"].append({
                    "id": row.id,
                    "drone_id": row.drone_id,
                    "spawn_time": row.spawn_time.strftime("%d.%m.%Y %H:%M:%S") if row.spawn_time else "-",
                    "downed_time": row.downed_time.strftime("%d.%m.%Y %H:%M:%S") if row.downed_time else "-",
                    "spawn_coords": f"{row.spawn_lat:.4f}°, {row.spawn_lon:.4f}°",
                    "target_name": row.target_name,
                    "interceptor_name": row.interceptor_name,
                    "crash_coords": f"{row.crash_lat:.4f}°, {row.crash_lon:.4f}°",
                    "crash_zone": row.crash_zone,
                    "status": row.status
                })

            count_res = await session.execute(select(func.count()).select_from(DownedDroneModel))
            payload["total_downed_count"] = int(count_res.scalar() or 0)

            if db_dirty:
                await session.commit()
            else:
                await session.rollback()

        for conn in list(active_connections):
            try:
                await conn.send_json(_sanitize(payload))
            except Exception:
                active_connections.remove(conn)


def _sanitize(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sanitize(v) for v in o]
    return o


# --- REST API ---

@app.get("/api/v1/downed_drones")
async def get_downed_drones():
    async with async_session() as session:
        res = await session.execute(select(DownedDroneModel).order_by(desc(DownedDroneModel.id)))
        items = res.scalars().all()
        return [
            {
                "id": r.id,
                "drone_id": r.drone_id,
                "spawn_time": r.spawn_time.strftime("%d.%m.%Y %H:%M:%S") if r.spawn_time else "-",
                "downed_time": r.downed_time.strftime("%d.%m.%Y %H:%M:%S") if r.downed_time else "-",
                "spawn_coords": f"{r.spawn_lat:.5f}°, {r.spawn_lon:.5f}°",
                "target_name": r.target_name,
                "interceptor_name": r.interceptor_name,
                "crash_coords": f"{r.crash_lat:.5f}°, {r.crash_lon:.5f}°",
                "crash_zone": r.crash_zone,
                "status": r.status
            }
            for r in items
        ]

@app.delete("/api/v1/downed_drones")
async def clear_downed_drones():
    async with async_session() as session:
        await session.execute(delete(DownedDroneModel))
        await session.commit()
    return {"status": "cleared"}

@app.delete("/api/v1/downed_drones/{drone_id}")
async def delete_downed_drone(drone_id: int):
    async with async_session() as session:
        await session.execute(delete(DownedDroneModel).where(DownedDroneModel.id == drone_id))
        await session.commit()
    return {"status": "deleted"}

@app.post("/api/v1/simulation/toggle")
async def toggle_simulation():
    global simulation_active, sim_start_time
    simulation_active = not simulation_active
    if simulation_active:
        sim_start_time = time.time()
    return {"simulation_active": simulation_active}

@app.post("/api/v1/simulation/reset")
async def reset_simulation():
    global sim_start_time, active_trackers, simulated_drone, _recent_events
    sim_start_time = time.time()
    active_trackers.clear()
    _recent_events.clear()
    simulated_drone.spawn_random()
    return {"status": "reset", "drone_id": simulated_drone.id}

@app.post("/api/v1/ew/toggle_autotracking")
async def toggle_autotracking():
    global auto_tracking_enabled
    auto_tracking_enabled = not auto_tracking_enabled
    return {"auto_tracking": auto_tracking_enabled}

@app.post("/api/v1/zones/reset_full_grid")
async def reset_zones_grid():
    async with async_session() as session:
        await session.execute(delete(TacticalZoneModel))
        await session.execute(delete(EWNodeModel))
        await session.execute(delete(TacticalSensorModel))
        await session.commit()
    return {"status": "grid_cleared"}

@app.post("/api/v1/zones/generate_from_h3")
async def generate_zones_from_h3():
    zones_data = generate_district_zones_from_h3()
    if not zones_data:
        return {"status": "error", "message": "Дані H3 відсутні або порожні"}

    async with async_session() as session:
        await session.execute(delete(TacticalZoneModel))
        for z in zones_data:
            model = TacticalZoneModel(
                name=z["name"],
                zone_type=z["zone_type"],
                coordinates=json.dumps(z["coordinates"])
            )
            session.add(model)
        await session.commit()

    return {"status": "success", "count": len(zones_data)}

@app.post("/api/v1/zones")
async def create_tactical_zone(zone: TacticalZoneCreate):
    async with async_session() as session:
        db_zone = TacticalZoneModel(
            name=zone.name, 
            zone_type=zone.zone_type, 
            coordinates=json.dumps(zone.coordinates)
        )
        session.add(db_zone)
        await session.commit()
        await session.refresh(db_zone)
        return {"status": "created", "id": db_zone.id}

@app.delete("/api/v1/zones/{zone_id}")
async def delete_tactical_zone(zone_id: int):
    async with async_session() as session:
        await session.execute(delete(TacticalZoneModel).where(TacticalZoneModel.id == zone_id))
        await session.commit()
        return {"status": "deleted"}

@app.get("/api/v1/risk/at")
async def risk_at(lat: float, lon: float):
    from shapely.geometry import Polygon as Poly
    async with async_session() as session:
        qz = await session.execute(select(TacticalZoneModel))
        dz = qz.scalars().all()
        qs = await session.execute(select(TacticalSensorModel))
        ci = []
        for s in qs.scalars().all():
            if s.sensor_type == "target_asset":
                cx, cy, _ = latlon_to_enu(s.lat, s.lon, s.alt)
                ci.append({"name": s.name, "x": cx, "y": cy})
        safe, caution, dang = [], [], []
        for z in dz:
            try:
                pts = [latlon_to_enu(p[0], p[1])[:2] for p in json.loads(z.coordinates)]
                poly = Poly(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if z.zone_type == "safe":
                    safe.append(poly)
                elif z.zone_type == "caution":
                    caution.append(poly)
                else:
                    dang.append(poly)
            except Exception:
                continue
    x, y, _ = latlon_to_enu(lat, lon, 0.0)
    s = risk_safety_at_enu(x, y, lat, lon, safe, caution, dang, ci)
    return {"lat": lat, "lon": lon, "safety": round(s * 100.0, 1)}

@app.get("/api/v1/risk/grid")
async def risk_grid(limit: int = 3000):
    return {"cells": risk_grid_cells(limit)}

@app.post("/api/v1/sensors")
async def create_tactical_sensor(sensor: TacticalSensorCreate):
    async with async_session() as session:
        db_sensor = TacticalSensorModel(
            name=sensor.name, 
            sensor_type=sensor.sensor_type, 
            lat=sensor.lat, 
            lon=sensor.lon, 
            alt=sensor.alt, 
            detection_radius=sensor.detection_radius, 
            description=sensor.description or ""
        )
        session.add(db_sensor)
        await session.commit()
        await session.refresh(db_sensor)
        return {"status": "created", "id": db_sensor.id}

@app.delete("/api/v1/sensors/{sensor_id}")
async def delete_tactical_sensor(sensor_id: int):
    async with async_session() as session:
        await session.execute(delete(TacticalSensorModel).where(TacticalSensorModel.id == sensor_id))
        await session.commit()
        return {"status": "deleted"}

@app.post("/api/v1/ew/node")
async def create_ew_node(node: EWNodeCreate):
    async with async_session() as session:
        db_node = EWNodeModel(
            name=node.name, 
            lat=node.lat, 
            lon=node.lon, 
            alt=node.alt, 
            max_range=node.max_range, 
            beamwidth=node.beamwidth, 
            current_azimuth=node.current_azimuth, 
            is_armed=True
        )
        session.add(db_node)
        await session.commit()
        await session.refresh(db_node)
        return {"status": "created", "id": db_node.id}

@app.delete("/api/v1/ew/node/{node_id}")
async def delete_ew_node(node_id: int):
    async with async_session() as session:
        await session.execute(delete(EWNodeModel).where(EWNodeModel.id == node_id))
        await session.commit()
        return {"status": "deleted"}

@app.post("/api/v1/ew/arm")
async def control_ew_node(cmd: ArmEWCommand):
    async with async_session() as session:
        res = await session.execute(select(EWNodeModel).where(EWNodeModel.id == cmd.node_id))
        node = res.scalars().first()
        if not node:
            return {"error": "Node not found"}

        gen = _burst_generations.get(cmd.node_id, 0) + 1
        _burst_generations[cmd.node_id] = gen
        node.is_armed = cmd.arm
        if cmd.arm:
            node.is_transmitting = True
            await session.commit()

            async def burst_shutdown(nid: int, sec: int, want_gen: int):
                await asyncio.sleep(sec)
                if _burst_generations.get(nid) != want_gen:
                    return
                async with async_session() as s:
                    q = await s.execute(select(EWNodeModel).where(EWNodeModel.id == nid))
                    n = q.scalars().first()
                    if n and _burst_generations.get(nid) == want_gen:
                        n.is_transmitting = False
                        await s.commit()

            asyncio.create_task(burst_shutdown(node.id, cmd.burst_duration, gen))
        else:
            node.is_transmitting = False
            await session.commit()

        return {"status": "success", "is_armed": node.is_armed, "transmitting": node.is_transmitting}

@app.patch("/api/v1/ew/node/{node_id}")
async def update_ew_node(node_id: int, update: EWNodeUpdate):
    async with async_session() as session:
        res = await session.execute(select(EWNodeModel).where(EWNodeModel.id == node_id))
        node = res.scalars().first()
        if not node:
            return {"error": "Node not found"}
        
        if update.name is not None: node.name = update.name
        if update.lat is not None: node.lat = update.lat
        if update.lon is not None: node.lon = update.lon
        if update.alt is not None: node.alt = update.alt
        if update.current_azimuth is not None: node.current_azimuth = update.current_azimuth
        if update.beamwidth is not None: node.beamwidth = update.beamwidth
        if update.max_range is not None: node.max_range = update.max_range
            
        await session.commit()
        return {"status": "updated", "id": node.id}

@app.patch("/api/v1/sensors/{sensor_id}")
async def update_tactical_sensor(sensor_id: int, update: TacticalSensorUpdate):
    async with async_session() as session:
        res = await session.execute(select(TacticalSensorModel).where(TacticalSensorModel.id == sensor_id))
        sensor = res.scalars().first()
        if not sensor:
            return {"error": "Sensor not found"}
            
        if update.name is not None: sensor.name = update.name
        if update.sensor_type is not None: sensor.sensor_type = update.sensor_type
        if update.lat is not None: sensor.lat = update.lat
        if update.lon is not None: sensor.lon = update.lon
        if update.alt is not None: sensor.alt = update.alt
        if update.detection_radius is not None: sensor.detection_radius = update.detection_radius
        if update.description is not None: sensor.description = update.description
            
        await session.commit()
        return {"status": "updated", "id": sensor.id}

@app.patch("/api/v1/zones/{zone_id}")
async def update_tactical_zone(zone_id: int, update: TacticalZoneUpdate):
    async with async_session() as session:
        res = await session.execute(select(TacticalZoneModel).where(TacticalZoneModel.id == zone_id))
        zone = res.scalars().first()
        if not zone:
            return {"error": "Zone not found"}
            
        if update.name is not None: zone.name = update.name
        if update.zone_type is not None: zone.zone_type = update.zone_type
        if update.coordinates is not None: zone.coordinates = json.dumps(update.coordinates)
            
        await session.commit()
        return {"status": "updated", "id": zone.id}

@app.websocket("/ws/tactical")
async def websocket_tactical(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

@app.post("/api/v1/seed")
async def run_seed_endpoint():
    from seed_district import seed as run_seed
    await run_seed()
    return {"status": "seed_completed"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        ok = risk_load_grid()
        logger.info("risk_h3 grid loaded=%s", ok)
    except Exception as e:
        logger.warning("risk_h3 load failed: %s", e)

    # Автоматичний запуск оптимізації розташування комплексів РЕБ при старті
    try:
        logger.info("Запуск первинної оптимізації розташування РЕБ...")
        await auto_optimize_and_apply_ew(node_count=5, replace_existing=False)
    except Exception as e:
        logger.error("Помилка автоматичної оптимізації РЕБ: %s", e)

    bg_task = asyncio.create_task(c2_calculation_loop())
    yield
    bg_task.cancel()

@app.post("/api/v1/ew/optimize")
async def trigger_ew_optimization(node_count: int = 7, replace: bool = True):
    """Ендпоінт для повторного розрахунку оптимального розміщення комплексів РЕБ."""
    results = await auto_optimize_and_apply_ew(node_count=node_count, replace_existing=replace)
    return {"status": "success", "count": len(results), "nodes": results}
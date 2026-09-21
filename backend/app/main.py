# backend/app/main.py
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
from app.hardware.pelco import PelcoDController

logger = logging.getLogger(__name__)


class DroneSimulation:
    def __init__(self):
        self.t_sim = 0.0
        self.spawn_random()

    def spawn_random(self):
        angle_deg = random.uniform(-75.0, 75.0)
        dist = random.uniform(8000.0, 15000.0)
        rad = math.radians(angle_deg)

        self.x = dist * math.sin(rad)
        self.y = dist * math.cos(rad)
        self.z = random.uniform(170.0, 260.0)

        self.spawn_lat, self.spawn_lon, _ = enu_to_latlon(self.x, self.y, self.z)
        self.spawn_time = datetime.now()

        targets = [
            ("ТЕЦ-6", latlon_to_enu(settings.DATUM_LAT + 0.065, settings.DATUM_LON + 0.080)[:2]),
            ("Київська ГЕС", latlon_to_enu(settings.DATUM_LAT + 0.150, settings.DATUM_LON - 0.035)[:2]),
            ("ПС 750кВ «Північна»", latlon_to_enu(settings.DATUM_LAT + 0.120, settings.DATUM_LON + 0.170)[:2]),
            ("Ж/М Троєщина", latlon_to_enu(settings.DATUM_LAT + 0.050, settings.DATUM_LON + 0.050)[:2]),
            ("Ж/М Оболонь", latlon_to_enu(settings.DATUM_LAT + 0.060, settings.DATUM_LON - 0.020)[:2]),
            ("Урядовий квартал", latlon_to_enu(settings.DATUM_LAT, settings.DATUM_LON)[:2]),
        ]
        target_item = random.choice(targets)
        self.target_name = target_item[0]
        tgt_x, tgt_y = target_item[1]
        tgt_x += random.uniform(-1500.0, 1500.0)
        tgt_y += random.uniform(-1500.0, 1500.0)

        dx = tgt_x - self.x
        dy = tgt_y - self.y
        dist_to_tgt = math.hypot(dx, dy)

        speed = random.uniform(49.0, 54.0)
        self.vx = (dx / dist_to_tgt) * speed
        self.vy = (dy / dist_to_tgt) * speed
        self.vz = 0.0

        self.status = "CRUISING"  # "CRUISING" | "JAMMED" | "CRASHED"
        self.id = f"SHAHED-{random.randint(101, 999)}"
        self.crashed_timer = 0.0
        self.interceptor_name = "Невідомо"
        self.downed_saved = False

    def apply_jamming(self, interceptor_name: str):
        if self.status == "CRUISING":
            self.status = "JAMMED"
            self.interceptor_name = interceptor_name
            self.vz = -random.uniform(6.0, 8.5)

    def step(self, dt: float):
        if self.status == "CRASHED":
            self.crashed_timer += dt
            if self.crashed_timer >= 4.0:
                self.spawn_random()
            return

        if self.status == "JAMMED":
            self.x += (self.vx * 0.82 + settings.WIND_VECTOR_X) * dt
            self.y += (self.vy * 0.82 + settings.WIND_VECTOR_Y) * dt
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
        turb_x = math.sin(self.t_sim / 4.0) * 0.4
        turb_y = math.cos(self.t_sim / 4.0) * 0.4
        self.x += (self.vx + turb_x) * dt
        self.y += (self.vy + turb_y) * dt

        if math.hypot(self.x, self.y) > 45000:
            self.spawn_random()

simulated_drone = DroneSimulation()
active_trackers: Dict[str, DroneKalmanFilter] = {}
active_connections: list[WebSocket] = []

simulation_active = True
sim_start_time = time.time()
auto_tracking_enabled = True

_zone_cache: Dict = {"fp": None, "safe": [], "danger": [], "items": []}
_burst_generations: Dict[int, int] = {}

async def populate_tactical_database(session):
    b_lat = settings.DATUM_LAT
    b_lon = settings.DATUM_LON

    ew_nodes = [
        EWNodeModel(name="РЕБ-1 «ДЕСНА-ЗАХІД»", lat=b_lat + 0.078, lon=b_lon - 0.008, alt=35.0, max_range=5500.0, beamwidth=35.0, current_azimuth=38.0, is_armed=True),
        EWNodeModel(name="РЕБ-2 «ДЕСНА-СХІД»", lat=b_lat + 0.085, lon=b_lon + 0.055, alt=28.0, max_range=5000.0, beamwidth=40.0, current_azimuth=345.0, is_armed=True),
        EWNodeModel(name="РЕБ-3 «КИЇВСЬКЕ МОРЕ»", lat=b_lat + 0.160, lon=b_lon - 0.030, alt=40.0, max_range=6000.0, beamwidth=45.0, current_azimuth=15.0, is_armed=True),
        EWNodeModel(name="РЕБ-4 «БРОВАРИ-РУБІЖ»", lat=b_lat + 0.082, lon=b_lon + 0.125, alt=22.0, max_range=4800.0, beamwidth=35.0, current_azimuth=25.0, is_armed=True)
    ]
    session.add_all(ew_nodes)

    zones = [
        TacticalZoneModel(name="Місто Київ: Правобережжя (Центр & Поділ)", zone_type="danger", coordinates=json.dumps([[b_lat - 0.08, b_lon - 0.12], [b_lat + 0.04, b_lon - 0.12], [b_lat + 0.04, b_lon + 0.01], [b_lat - 0.08, b_lon + 0.01]])),
        TacticalZoneModel(name="Місто Київ: Оболонь & Пріорка", zone_type="danger", coordinates=json.dumps([[b_lat + 0.04, b_lon - 0.08], [b_lat + 0.10, b_lon - 0.08], [b_lat + 0.10, b_lon - 0.01], [b_lat + 0.04, b_lon - 0.01]])),
        TacticalZoneModel(name="Місто Київ: Троєщина & Райдужний", zone_type="danger", coordinates=json.dumps([[b_lat + 0.03, b_lon + 0.04], [b_lat + 0.09, b_lon + 0.04], [b_lat + 0.09, b_lon + 0.10], [b_lat + 0.03, b_lon + 0.10]])),
        TacticalZoneModel(name="Місто Київ: Дарниця & Лівобережний кластер", zone_type="danger", coordinates=json.dumps([[b_lat - 0.08, b_lon + 0.03], [b_lat + 0.03, b_lon + 0.03], [b_lat + 0.03, b_lon + 0.13], [b_lat - 0.08, b_lon + 0.13]])),
        TacticalZoneModel(name="Місто Вишгород & ГЕС (Стратегічний вузол)", zone_type="danger", coordinates=json.dumps([[b_lat + 0.11, b_lon - 0.07], [b_lat + 0.16, b_lon - 0.07], [b_lat + 0.16, b_lon - 0.01], [b_lat + 0.11, b_lon - 0.01]])),
        TacticalZoneModel(name="Місто Бровари & Індустріальний парк", zone_type="danger", coordinates=json.dumps([[b_lat + 0.03, b_lon + 0.13], [b_lat + 0.08, b_lon + 0.13], [b_lat + 0.08, b_lon + 0.23], [b_lat + 0.03, b_lon + 0.23]])),
        TacticalZoneModel(name="Прибережна лінія: Нові & Старі Петрівці", zone_type="danger", coordinates=json.dumps([[b_lat + 0.16, b_lon - 0.09], [b_lat + 0.23, b_lon - 0.09], [b_lat + 0.23, b_lon - 0.04], [b_lat + 0.16, b_lon - 0.04]])),
        TacticalZoneModel(name="Селищний масив: Хотянівка, Зазим'я, Пухівка", zone_type="danger", coordinates=json.dumps([[b_lat + 0.08, b_lon + 0.04], [b_lat + 0.14, b_lon + 0.04], [b_lat + 0.14, b_lon + 0.09], [b_lat + 0.08, b_lon + 0.09]])),
        TacticalZoneModel(name="Енергетичний кластер ТЕЦ-6", zone_type="danger", coordinates=json.dumps([[b_lat + 0.05, b_lon + 0.07], [b_lat + 0.08, b_lon + 0.07], [b_lat + 0.08, b_lon + 0.11], [b_lat + 0.05, b_lon + 0.11]])),

        TacticalZoneModel(name="KILLBOX-1: Акваторія Київського Моря", zone_type="safe", coordinates=json.dumps([[b_lat + 0.16, b_lon - 0.04], [b_lat + 0.25, b_lon - 0.04], [b_lat + 0.25, b_lon + 0.05], [b_lat + 0.16, b_lon + 0.05]])),
        TacticalZoneModel(name="KILLBOX-2: Заплава р. Десна (Острови & Луки)", zone_type="safe", coordinates=json.dumps([[b_lat + 0.09, b_lon - 0.01], [b_lat + 0.16, b_lon - 0.01], [b_lat + 0.16, b_lon + 0.04], [b_lat + 0.09, b_lon + 0.04]])),
        TacticalZoneModel(name="KILLBOX-3: Вишгородський лісовий масив", zone_type="safe", coordinates=json.dumps([[b_lat + 0.10, b_lon - 0.18], [b_lat + 0.24, b_lon - 0.18], [b_lat + 0.24, b_lon - 0.09], [b_lat + 0.10, b_lon - 0.09]])),
        TacticalZoneModel(name="KILLBOX-4: Північно-Броварські торфовища & поля", zone_type="safe", coordinates=json.dumps([[b_lat + 0.08, b_lon + 0.09], [b_lat + 0.18, b_lon + 0.09], [b_lat + 0.18, b_lon + 0.23], [b_lat + 0.08, b_lon + 0.23]])),
        TacticalZoneModel(name="KILLBOX-5: Броварський лісопарк (Буфер Київ-Бровари)", zone_type="safe", coordinates=json.dumps([[b_lat + 0.03, b_lon + 0.10], [b_lat + 0.08, b_lon + 0.10], [b_lat + 0.08, b_lon + 0.13], [b_lat + 0.03, b_lon + 0.13]])),
        TacticalZoneModel(name="KILLBOX-6: Природний буфер Муромець-Труханів", zone_type="safe", coordinates=json.dumps([[b_lat + 0.02, b_lon + 0.01], [b_lat + 0.09, b_lon + 0.01], [b_lat + 0.09, b_lon + 0.04], [b_lat + 0.02, b_lon + 0.04]])),
        TacticalZoneModel(name="KILLBOX-7: Калитянський агросектор (Схід)", zone_type="safe", coordinates=json.dumps([[b_lat + 0.14, b_lon + 0.04], [b_lat + 0.24, b_lon + 0.04], [b_lat + 0.24, b_lon + 0.23], [b_lat + 0.14, b_lon + 0.23]]))
    ]
    session.add_all(zones)

    sensors = [
        TacticalSensorModel(name="ТЕЦ-6 (Критична інфраструктура)", sensor_type="target_asset", lat=b_lat + 0.065, lon=b_lon + 0.080, detection_radius=1000.0, description="Стратегічний об'єкт генерації"),
        TacticalSensorModel(name="Київська ГЕС (Дамба)", sensor_type="target_asset", lat=b_lat + 0.150, lon=b_lon - 0.035, detection_radius=1200.0, description="Стратегічний гідровузол"),
        TacticalSensorModel(name="ПС 750кВ «Північна»", sensor_type="target_asset", lat=b_lat + 0.120, lon=b_lon + 0.170, detection_radius=800.0, description="Вузлова підстанція Укренерго"),
        TacticalSensorModel(name="CAM-PTZ-01 «ВИШКА-ДЕСНА»", sensor_type="camera", lat=b_lat + 0.105, lon=b_lon + 0.015, detection_radius=3500.0, description="Тепловізор на вежі 75м"),
        TacticalSensorModel(name="CAM-PTZ-02 «КИЇВСЬКЕ МОРЕ»", sensor_type="camera", lat=b_lat + 0.165, lon=b_lon - 0.045, detection_radius=4000.0, description="Оптичний канал акваторії"),
        TacticalSensorModel(name="AUDIO-ARRAY-11 «ПОГРЕБИ»", sensor_type="acoustic", lat=b_lat + 0.095, lon=b_lon + 0.060, detection_radius=3800.0, description="Акустичний пеленгатор MD-550"),
        TacticalSensorModel(name="AUDIO-ARRAY-12 «ЛІТКИ»", sensor_type="acoustic", lat=b_lat + 0.160, lon=b_lon + 0.080, detection_radius=4500.0, description="Передовий акустичний пост"),
        TacticalSensorModel(name="МВГ «ХИЖАК-1»", sensor_type="observation_post", lat=b_lat + 0.115, lon=b_lon + 0.005, detection_radius=2200.0, description="Мобільна вогнева група")
    ]
    session.add_all(sensors)
    await session.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with async_session() as session:
        res = await session.execute(select(EWNodeModel))
        if not res.scalars().first():
            await populate_tactical_database(session)
            
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
    global sim_start_time, auto_tracking_enabled, simulated_drone, active_trackers
    last_loop_time = time.time()
    
    while True:
        await asyncio.sleep(0.5)
        now = time.time()
        dt = min(1.0, max(0.1, now - last_loop_time))
        last_loop_time = now

        if simulation_active:
            simulated_drone.step(dt)
            target_key = simulated_drone.id
            sx_sim, sy_sim, sz_sim = simulated_drone.x, simulated_drone.y, simulated_drone.z

            # Очищуємо старі неактивні трекери
            for old_id in list(active_trackers.keys()):
                if old_id != target_key:
                    active_trackers.pop(old_id, None)

            if target_key not in active_trackers:
                tracker = DroneKalmanFilter(sx_sim, sy_sim, sz_sim)
                active_trackers[target_key] = tracker
            else:
                active_trackers[target_key].predict(dt)
                noisy_meas = np.array([
                    sx_sim + float(np.random.normal(0.0, 8.0)),
                    sy_sim + float(np.random.normal(0.0, 8.0)),
                    sz_sim + float(np.random.normal(0.0, 3.0)),
                ])
                active_trackers[target_key].update(noisy_meas)

        payload = {
            "tracks": [],
            "ew_nodes": [],
            "zones": [],
            "sensors": [],
            "timestamp": now,
            "simulation_active": simulation_active,
            "auto_tracking": auto_tracking_enabled,
            "emergency_override": False,
            "threat_info": None,
            "recent_downed": [],
            "total_downed_count": 0
        }

        async with async_session() as session:
            db_dirty = False
            # 1. Завантаження зон
            q_zones = await session.execute(select(TacticalZoneModel))
            db_zones = q_zones.scalars().all()
            zone_fp = tuple((z.id, z.zone_type, z.coordinates) for z in db_zones)
            if _zone_cache["fp"] != zone_fp:
                safe_shapely = []
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
                    else:
                        danger_shapely.append(poly)
                _zone_cache["fp"] = zone_fp
                _zone_cache["safe"] = safe_shapely
                _zone_cache["danger"] = danger_shapely
                _zone_cache["items"] = items
            else:
                safe_shapely = _zone_cache["safe"]
                danger_shapely = _zone_cache["danger"]

            for z in db_zones:
                payload["zones"].append({
                    "id": z.id,
                    "name": z.name,
                    "zone_type": z.zone_type,
                    "coordinates": json.loads(z.coordinates)
                })

            # 2. Сенсори та критичні об'єкти
            q_sensors = await session.execute(select(TacticalSensorModel))
            ci_assets = []
            for s in q_sensors.scalars().all():
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

            # 3. Збереження збитого дрона в БД (Permanent Crash Record)
            if simulated_drone.status == "CRASHED" and not simulated_drone.downed_saved:
                c_lat, c_lon, _ = enu_to_latlon(simulated_drone.x, simulated_drone.y, 0.0)
                pt = Point(simulated_drone.x, simulated_drone.y)
                crash_zone_name = "Відкрита місцевість"

                for poly, zname, ztype in _zone_cache["items"]:
                    try:
                        if poly.contains(pt):
                            crash_zone_name = f"{'🟢 ' if ztype == 'safe' else '🔴 '}{zname}"
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

            # 4. Обробка треків та оцінка загрози
            primary_target = None
            for target_id, tracker in list(active_trackers.items()):
                if not simulation_active:
                    tracker.predict(dt)

                sx, sy, sz = tracker.state[0], tracker.state[1], tracker.state[2]
                vx, vy, vz = tracker.state[3], tracker.state[4], tracker.state[5]
                speed = float(np.sqrt(vx**2 + vy**2 + vz**2))

                t_lat, t_lon, t_alt = enu_to_latlon(sx, sy, sz)
                p30_x, p30_y, _ = tracker.extrapolate(30.0)
                p60_x, p60_y, _ = tracker.extrapolate(60.0)

                lat_30, lon_30, _ = enu_to_latlon(p30_x, p30_y, sz)
                lat_60, lon_60, _ = enu_to_latlon(p60_x, p60_y, sz)

                imp_x, imp_y, t_fall = InterceptionPlanner.predict_crash_point(sx, sy, sz, vx, vy, vz)
                imp_lat, imp_lon, _ = enu_to_latlon(imp_x, imp_y, 0)
                is_safe = InterceptionPlanner.is_safe_drop(imp_x, imp_y, safe_shapely, danger_shapely)

                is_ci_critical, min_dist_ci, nearest_ci_name = InterceptionPlanner.evaluate_ci_proximity(sx, sy, ci_assets, threshold_m=2500.0)
                heading = (np.degrees(np.arctan2(vx, vy)) + 360.0) % 360.0

                track_data = {
                    "id": target_id,
                    "status": simulated_drone.status,
                    "lat": t_lat,
                    "lon": t_lon,
                    "alt": max(0.0, t_alt),
                    "speed": speed if simulated_drone.status != "CRASHED" else 0.0,
                    "heading": heading,
                    "predicted_30s": [lat_30, lon_30] if simulated_drone.status != "CRASHED" else [t_lat, t_lon],
                    "predicted_60s": [lat_60, lon_60] if simulated_drone.status != "CRASHED" else [t_lat, t_lon],
                    "crash_point": [imp_lat, imp_lon],
                    "is_safe_to_engage": is_safe if simulated_drone.status == "CRUISING" else False,
                    "is_ci_critical": is_ci_critical if simulated_drone.status == "CRUISING" else False,
                    "ci_distance": round(min_dist_ci, 0),
                    "nearest_ci": nearest_ci_name,
                    "target_asset_name": simulated_drone.target_name,
                    "raw_enu": [sx, sy, sz, vx, vy, vz]
                }
                payload["tracks"].append(track_data)
                primary_target = track_data

            # 5. Динамічне наведення та збиття дрона РЕБ
            q_nodes = await session.execute(select(EWNodeModel))
            db_nodes = q_nodes.scalars().all()
            
            best_interceptor_id = None
            best_interceptor_name = "РЕБ"
            min_ew_dist = float('inf')

            for node in db_nodes:
                node_x, node_y, node_z = latlon_to_enu(node.lat, node.lon, node.alt)
                distance = float('inf')
                target_azimuth = node.current_azimuth
                elevation = 0.0
                lead_x = lead_y = lead_z = None
                has_lead = False

                if primary_target and auto_tracking_enabled:
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
                            best_interceptor_name = node.name

                        _pelco_cmd = PelcoDController.build_pan_tilt_command(
                            address=node.id,
                            pan_speed=int(min(63, max(10, abs(vx) * 0.8))),
                            tilt_speed=20,
                            left=(az_diff < 0.0),
                            up=(elevation > 15.0)
                        )
                        logger.debug("pelco node=%s az=%.1f el=%.1f cmd=%s", node.id, target_azimuth, elevation, _pelco_cmd.hex())

                # Бойове придушення
                if primary_target and primary_target["status"] == "CRUISING":
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

                if primary_target and primary_target["status"] == "CRASHED":
                    if node.is_transmitting:
                        node.is_transmitting = False
                        db_dirty = True

                # Фіксація влучання РЕБ
                if node.is_transmitting and primary_target and primary_target["status"] == "CRUISING":
                    angle_diff = abs((target_azimuth - node.current_azimuth + 180.0) % 360.0 - 180.0)
                    if distance <= node.max_range and angle_diff <= (node.beamwidth / 2.0 + 4.0):
                        simulated_drone.apply_jamming(node.name)
                        payload["threat_info"] = f"⚡ ВЛУЧАННЯ РЕБ: {node.name} зірвав наведення {simulated_drone.id}!"

                lead_coord = None
                if (has_lead and lead_x is not None and lead_y is not None and lead_z is not None
                        and primary_target and primary_target["status"] != "CRASHED"
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

            # 6. Останні 5 збитих дронів та лічильник
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
                await conn.send_json(payload)
            except Exception:
                active_connections.remove(conn)

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
    global sim_start_time, active_trackers, simulated_drone
    sim_start_time = time.time()
    active_trackers.clear()
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
        await populate_tactical_database(session)
    return {"status": "full_grid_deployed"}

@app.post("/api/v1/zones")
async def create_tactical_zone(zone: TacticalZoneCreate):
    async with async_session() as session:
        db_zone = TacticalZoneModel(name=zone.name, zone_type=zone.zone_type, coordinates=json.dumps(zone.coordinates))
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

@app.post("/api/v1/sensors")
async def create_tactical_sensor(sensor: TacticalSensorCreate):
    async with async_session() as session:
        db_sensor = TacticalSensorModel(name=sensor.name, sensor_type=sensor.sensor_type, lat=sensor.lat, lon=sensor.lon, alt=sensor.alt, detection_radius=sensor.detection_radius, description=sensor.description or "")
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
        db_node = EWNodeModel(name=node.name, lat=node.lat, lon=node.lon, alt=node.alt, max_range=node.max_range, beamwidth=node.beamwidth, current_azimuth=node.current_azimuth, is_armed=True)
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

@app.post("/api/v1/telemetry")
async def ingest_detection(item: DetectionCreate):
    global active_trackers
    x, y, z = latlon_to_enu(item.lat, item.lon, item.alt)
    target_key = "EXTERNAL-DETECTION"

    if target_key not in active_trackers:
        tracker = DroneKalmanFilter(x, y, z)
        active_trackers[target_key] = tracker
    else:
        active_trackers[target_key].update(np.array([x, y, z]))

    return {"status": "accepted", "target_key": target_key}

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
        
        if update.name is not None:
            node.name = update.name
        if update.lat is not None:
            node.lat = update.lat
        if update.lon is not None:
            node.lon = update.lon
        if update.alt is not None:
            node.alt = update.alt
        if update.current_azimuth is not None:
            node.current_azimuth = update.current_azimuth
        if update.beamwidth is not None:
            node.beamwidth = update.beamwidth
        if update.max_range is not None:
            node.max_range = update.max_range
            
        await session.commit()
        return {"status": "updated", "id": node.id}

@app.patch("/api/v1/sensors/{sensor_id}")
async def update_tactical_sensor(sensor_id: int, update: TacticalSensorUpdate):
    async with async_session() as session:
        res = await session.execute(select(TacticalSensorModel).where(TacticalSensorModel.id == sensor_id))
        sensor = res.scalars().first()
        if not sensor:
            return {"error": "Sensor not found"}
            
        if update.name is not None:
            sensor.name = update.name
        if update.sensor_type is not None:
            sensor.sensor_type = update.sensor_type
        if update.lat is not None:
            sensor.lat = update.lat
        if update.lon is not None:
            sensor.lon = update.lon
        if update.alt is not None:
            sensor.alt = update.alt
        if update.detection_radius is not None:
            sensor.detection_radius = update.detection_radius
        if update.description is not None:
            sensor.description = update.description
            
        await session.commit()
        return {"status": "updated", "id": sensor.id}

@app.patch("/api/v1/zones/{zone_id}")
async def update_tactical_zone(zone_id: int, update: TacticalZoneUpdate):
    async with async_session() as session:
        res = await session.execute(select(TacticalZoneModel).where(TacticalZoneModel.id == zone_id))
        zone = res.scalars().first()
        if not zone:
            return {"error": "Zone not found"}
            
        if update.name is not None:
            zone.name = update.name
        if update.zone_type is not None:
            zone.zone_type = update.zone_type
        if update.coordinates is not None:
            zone.coordinates = json.dumps(update.coordinates)
            
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
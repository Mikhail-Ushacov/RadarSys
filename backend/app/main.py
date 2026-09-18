# backend/app/main.py
import asyncio
import json
import time
from typing import Dict, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from shapely.geometry import Polygon
from sqlalchemy import select, delete
import numpy as np

from app.config import settings
from app.database import init_db, async_session
from app.models import EWNodeModel, TacticalZoneModel, TacticalSensorModel
from app.schemas import (
    DetectionCreate, ArmEWCommand, EWNodeCreate, EWNodeUpdate,
    TacticalZoneCreate, TacticalZoneUpdate,
    TacticalSensorCreate, TacticalSensorUpdate
)
from app.core.geo import latlon_to_enu, enu_to_latlon
from app.core.kalman import DroneKalmanFilter
from app.core.planner import InterceptionPlanner

active_trackers: Dict[str, DroneKalmanFilter] = {}
active_connections: list[WebSocket] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    
    async with async_session() as session:
        # 1. Початковий РЕБ
        res = await session.execute(select(EWNodeModel))
        if not res.scalars().first():
            node = EWNodeModel(
                name="PRECISION-EW-ALPHA",
                lat=settings.DATUM_LAT + 0.012,
                lon=settings.DATUM_LON - 0.015,
                alt=25.0,
                max_range=4000.0,
                beamwidth=35.0,
                current_azimuth=45.0,
                is_armed=True
            )
            session.add(node)

        # 2. Початкові зони
        res_zones = await session.execute(select(TacticalZoneModel))
        if not res_zones.scalars().first():
            safe_poly = [
                [settings.DATUM_LAT + 0.02, settings.DATUM_LON - 0.06],
                [settings.DATUM_LAT + 0.05, settings.DATUM_LON - 0.06],
                [settings.DATUM_LAT + 0.05, settings.DATUM_LON - 0.02],
                [settings.DATUM_LAT + 0.02, settings.DATUM_LON - 0.02]
            ]
            danger_poly = [
                [settings.DATUM_LAT - 0.01, settings.DATUM_LON - 0.01],
                [settings.DATUM_LAT + 0.01, settings.DATUM_LON - 0.01],
                [settings.DATUM_LAT + 0.01, settings.DATUM_LON + 0.02],
                [settings.DATUM_LAT - 0.01, settings.DATUM_LON + 0.02]
            ]
            session.add(TacticalZoneModel(name="Полігон / Поля Північ", zone_type="safe", coordinates=json.dumps(safe_poly)))
            session.add(TacticalZoneModel(name="Густонаселений район", zone_type="danger", coordinates=json.dumps(danger_poly)))

        # 3. Базові сенсори
        res_sensors = await session.execute(select(TacticalSensorModel))
        if not res_sensors.scalars().first():
            session.add(TacticalSensorModel(
                name="CAM-OPTIC-01", sensor_type="camera",
                lat=settings.DATUM_LAT + 0.008, lon=settings.DATUM_LON + 0.005,
                detection_radius=2200.0, description="Тепловізійна PTZ камера"
            ))
            session.add(TacticalSensorModel(
                name="AUDIO-POST-4", sensor_type="acoustic",
                lat=settings.DATUM_LAT - 0.015, lon=settings.DATUM_LON - 0.012,
                detection_radius=3000.0, description="Акустичний масив мікрофонів"
            ))
            session.add(TacticalSensorModel(
                name="ТЕС-Центральна", sensor_type="target_asset",
                lat=settings.DATUM_LAT + 0.002, lon=settings.DATUM_LON + 0.018,
                detection_radius=500.0, description="Захищений об'єкт критичної енергетики"
            ))

        await session.commit()
            
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
    last_loop_time = time.time()
    
    while True:
        await asyncio.sleep(0.5)
        now = time.time()
        dt = now - last_loop_time
        last_loop_time = now

        payload = {
            "tracks": [],
            "ew_nodes": [],
            "zones": [],
            "sensors": [],
            "timestamp": now
        }

        async with async_session() as session:
            # 1. Зони
            q_zones = await session.execute(select(TacticalZoneModel))
            db_zones = q_zones.scalars().all()
            
            safe_shapely = []
            danger_shapely = []
            
            for z in db_zones:
                coords = json.loads(z.coordinates)
                enu_points = [latlon_to_enu(p[0], p[1])[:2] for p in coords]
                poly = Polygon(enu_points)
                if z.zone_type == "safe":
                    safe_shapely.append(poly)
                else:
                    danger_shapely.append(poly)

                payload["zones"].append({
                    "id": z.id,
                    "name": z.name,
                    "zone_type": z.zone_type,
                    "coordinates": coords
                })

            # 2. Сенсори
            q_sensors = await session.execute(select(TacticalSensorModel))
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

            # 3. РЕБ
            q_nodes = await session.execute(select(EWNodeModel))
            for node in q_nodes.scalars().all():
                payload["ew_nodes"].append({
                    "id": node.id,
                    "name": node.name,
                    "lat": node.lat,
                    "lon": node.lon,
                    "azimuth": node.current_azimuth,
                    "beamwidth": node.beamwidth,
                    "max_range": node.max_range,
                    "is_armed": node.is_armed,
                    "is_transmitting": node.is_transmitting
                })

        # 4. Треки
        for target_id, tracker in list(active_trackers.items()):
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

            payload["tracks"].append({
                "id": target_id,
                "lat": t_lat,
                "lon": t_lon,
                "alt": t_alt,
                "speed": speed,
                "heading": (np.degrees(np.arctan2(vx, vy)) + 360.0) % 360.0,
                "predicted_30s": [lat_30, lon_30],
                "predicted_60s": [lat_60, lon_60],
                "crash_point": [imp_lat, imp_lon],
                "is_safe_to_engage": is_safe
            })

        for conn in list(active_connections):
            try:
                await conn.send_json(payload)
            except Exception:
                active_connections.remove(conn)

# --- REST API ---

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

@app.post("/api/v1/telemetry")
async def ingest_detection(item: DetectionCreate):
    global active_trackers
    x, y, z = latlon_to_enu(item.lat, item.lon, item.alt)
    target_key = "TARGET-SHAHED-01"
    if target_key not in active_trackers:
        active_trackers[target_key] = DroneKalmanFilter(x, y, z)
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
            
        node.is_armed = cmd.arm
        if cmd.arm:
            node.is_transmitting = True
            await session.commit()
            
            async def burst_shutdown(nid: int, sec: int):
                await asyncio.sleep(sec)
                async with async_session() as s:
                    q = await s.execute(select(EWNodeModel).where(EWNodeModel.id == nid))
                    n = q.scalars().first()
                    if n:
                        n.is_transmitting = False
                        await s.commit()
            
            asyncio.create_task(burst_shutdown(node.id, cmd.burst_duration))
        else:
            node.is_transmitting = False
            await session.commit()

        return {"status": "success", "is_armed": node.is_armed, "transmitting": node.is_transmitting}

# --- ОНОВЛЕННЯ КООРДИНАТ ПРИ ПЕРЕТЯГУВАННІ (PATCH) ---

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
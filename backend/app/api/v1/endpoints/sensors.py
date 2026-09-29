# backend/app/api/v1/endpoints/sensors.py
from fastapi import APIRouter
from sqlalchemy import select, delete

from app.database import async_session
from app.models import TacticalSensorModel
from app.schemas import TacticalSensorCreate, TacticalSensorUpdate

router = APIRouter(prefix="/sensors", tags=["sensors"])

@router.post("")
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

@router.delete("/{sensor_id}")
async def delete_tactical_sensor(sensor_id: int):
    async with async_session() as session:
        await session.execute(delete(TacticalSensorModel).where(TacticalSensorModel.id == sensor_id))
        await session.commit()
        return {"status": "deleted"}

@router.patch("/{sensor_id}")
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
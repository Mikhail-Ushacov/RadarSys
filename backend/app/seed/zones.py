# backend/app/api/v1/endpoints/zones.py
import json
from fastapi import APIRouter
from sqlalchemy import select, delete

from app.database import async_session
from app.models import TacticalZoneModel, EWNodeModel, TacticalSensorModel
from app.schemas import TacticalZoneCreate, TacticalZoneUpdate
from app.core.risk_h3 import generate_district_zones_from_h3

router = APIRouter(prefix="/zones", tags=["zones"])

@router.post("")
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

@router.delete("/{zone_id}")
async def delete_tactical_zone(zone_id: int):
    async with async_session() as session:
        await session.execute(delete(TacticalZoneModel).where(TacticalZoneModel.id == zone_id))
        await session.commit()
        return {"status": "deleted"}

@router.patch("/{zone_id}")
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

@router.post("/reset_full_grid")
async def reset_zones_grid():
    async with async_session() as session:
        await session.execute(delete(TacticalZoneModel))
        await session.execute(delete(EWNodeModel))
        await session.execute(delete(TacticalSensorModel))
        await session.commit()
    return {"status": "grid_cleared"}

@router.post("/generate_from_h3")
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
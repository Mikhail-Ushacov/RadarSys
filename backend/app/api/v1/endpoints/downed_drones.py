# backend/app/api/v1/endpoints/downed_drones.py
from fastapi import APIRouter
from sqlalchemy import select, delete, desc

from app.database import async_session
from app.models import DownedDroneModel

router = APIRouter(prefix="/downed_drones", tags=["downed_drones"])

@router.get("")
async def get_downed_drones():
    async with async_session() as session:
        res = await session.execute(select(DownedDroneModel).order_by(desc(DownedDroneModel.id)))
        items = res.scalars().all()
        return [
            {
                "id": r.id,
                "drone_id": r.drone_id,
                "drone_type": getattr(r, "drone_type", "Shahed-136 (Герань-2)"),
                "spawn_time": r.spawn_time.strftime("%d.%m.%Y %H:%M:%S") if r.spawn_time else "-",
                "downed_time": r.downed_time.strftime("%d.%m.%Y %H:%M:%S") if r.downed_time else "-",
                "spawn_coords": f"{r.spawn_lat:.5f}°, {r.spawn_lon:.5f}°",
                "target_name": r.target_name,
                "interceptor_name": r.interceptor_name,
                "crash_coords": f"{r.crash_lat:.5f}°, {r.crash_lon:.5f}°",
                "crash_zone": r.crash_zone,
                "debris_radius_m": getattr(r, "debris_radius_m", 120.0),
                "emergency_112_called": getattr(r, "emergency_112_called", False),
                "emergency_details": getattr(r, "emergency_details", ""),
                "status": r.status
            }
            for r in items
        ]

@router.delete("")
async def clear_downed_drones():
    async with async_session() as session:
        await session.execute(delete(DownedDroneModel))
        await session.commit()
    return {"status": "cleared"}

@router.delete("/{drone_id}")
async def delete_downed_drone(drone_id: int):
    async with async_session() as session:
        await session.execute(delete(DownedDroneModel).where(DownedDroneModel.id == drone_id))
        await session.commit()
    return {"status": "deleted"}
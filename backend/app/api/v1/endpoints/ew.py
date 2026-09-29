# backend/app/api/v1/endpoints/ew.py
import asyncio
from fastapi import APIRouter
from sqlalchemy import select, delete

from app.database import async_session
from app.models import EWNodeModel
from app.schemas import EWNodeCreate, EWNodeUpdate, ArmEWCommand
from app.services.c2_engine import c2_engine
from app.seed.ew_optimizer import auto_optimize_and_apply_ew

router = APIRouter(prefix="/ew", tags=["ew"])

@router.post("/toggle_autotracking")
async def toggle_autotracking():
    auto_tracking = c2_engine.toggle_auto_tracking()
    return {"auto_tracking": auto_tracking}

@router.post("/node")
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

@router.delete("/node/{node_id}")
async def delete_ew_node(node_id: int):
    async with async_session() as session:
        await session.execute(delete(EWNodeModel).where(EWNodeModel.id == node_id))
        await session.commit()
        return {"status": "deleted"}

@router.patch("/node/{node_id}")
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

@router.post("/arm")
async def control_ew_node(cmd: ArmEWCommand):
    async with async_session() as session:
        res = await session.execute(select(EWNodeModel).where(EWNodeModel.id == cmd.node_id))
        node = res.scalars().first()
        if not node:
            return {"error": "Node not found"}

        gen = c2_engine.get_burst_generation(cmd.node_id)
        node.is_armed = cmd.arm
        if cmd.arm:
            node.is_transmitting = True
            await session.commit()

            async def burst_shutdown(nid: int, sec: int, want_gen: int):
                await asyncio.sleep(sec)
                if not c2_engine.is_current_burst_generation(nid, want_gen):
                    return
                async with async_session() as s:
                    q = await s.execute(select(EWNodeModel).where(EWNodeModel.id == nid))
                    n = q.scalars().first()
                    if n and c2_engine.is_current_burst_generation(nid, want_gen):
                        n.is_transmitting = False
                        await s.commit()

            asyncio.create_task(burst_shutdown(node.id, cmd.burst_duration, gen))
        else:
            node.is_transmitting = False
            await session.commit()

        return {"status": "success", "is_armed": node.is_armed, "transmitting": node.is_transmitting}

@router.post("/optimize")
async def trigger_ew_optimization(node_count: int = 7, replace: bool = True):
    results = await auto_optimize_and_apply_ew(node_count=node_count, replace_existing=replace)
    return {"status": "success", "count": len(results), "nodes": results}
# backend/app/api/v1/endpoints/simulation.py
from fastapi import APIRouter
from app.services.c2_engine import c2_engine

router = APIRouter(prefix="/simulation", tags=["simulation"])

@router.post("/toggle")
async def toggle_simulation():
    active = c2_engine.toggle_simulation()
    return {"simulation_active": active}

@router.post("/reset")
async def reset_simulation():
    drone_id = c2_engine.reset_simulation()
    return {"status": "reset", "drone_id": drone_id}
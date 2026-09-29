# backend/app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1.endpoints import (
    simulation,
    ew,
    sensors,
    downed_drones,
    risk,
    seed
)
from app.seed import zones

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(simulation.router)
api_v1_router.include_router(ew.router)
api_v1_router.include_router(zones.router)
api_v1_router.include_router(sensors.router)
api_v1_router.include_router(downed_drones.router)
api_v1_router.include_router(risk.router)
api_v1_router.include_router(seed.router)
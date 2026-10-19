# backend/app/api/v1/endpoints/data_source.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Literal

from app.services.c2_engine import c2_engine
from app.services.mapa_service import mapa_service

router = APIRouter(prefix="/source", tags=["data_source"])


class SetModeRequest(BaseModel):
    mode: Literal["simulation", "live_mapa"]


@router.get("/status")
async def get_data_source_status():
    """Повертає поточний статус джерела цілей."""
    return {
        "mode": c2_engine.source_mode,
        "mapa_mode": mapa_service.source_mode,
        "cached_targets_count": len(mapa_service.cached_raw_objects),
        "active_live_tracks": len(mapa_service.active_tracks),
        "last_sync": mapa_service.last_fetch_time,
    }


@router.post("/mode")
async def set_data_source_mode(req: SetModeRequest):
    """Перемикає джерело між симулятором та реальними даними mapa.ua."""
    c2_engine.set_source_mode(req.mode)
    if req.mode == "live_mapa":
        await mapa_service.fetch_threats()
        mapa_service.sync_tracks(mapa_service.cached_raw_objects)

    return {
        "status": "success",
        "current_mode": c2_engine.source_mode,
        "targets_count": len(mapa_service.active_tracks) if req.mode == "live_mapa" else 1
    }
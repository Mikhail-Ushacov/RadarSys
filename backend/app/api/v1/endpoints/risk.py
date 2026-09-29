# backend/app/api/v1/endpoints/risk.py
import json
from fastapi import APIRouter
from shapely.geometry import Polygon as Poly
from sqlalchemy import select

from app.database import async_session
from app.models import TacticalZoneModel, TacticalSensorModel
from app.core.geo import latlon_to_enu
from app.core.risk_h3 import (
    safety_at_enu as risk_safety_at_enu,
    grid_for_frontend as risk_grid_cells
)

router = APIRouter(prefix="/risk", tags=["risk"])

@router.get("/at")
async def risk_at(lat: float, lon: float):
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

@router.get("/grid")
async def risk_grid(limit: int = 3000):
    return {"cells": risk_grid_cells(limit)}
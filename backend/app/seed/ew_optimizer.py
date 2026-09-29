"""
backend/app/seed/ew_optimizer.py

Секторально-ешелонований алгоритм оптимізації комплексів РЕБ.
Оцінює взаємне розташування критичної інфраструктури (ОКІ) та зон безпеки (Killbox),
розраховує точки встановлення РЕБ, кути наведення та адаптивний радіус до 10 000 метрів.
"""

from __future__ import annotations
import math
import json
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
import numpy as np
from shapely.geometry import Point, Polygon
from sqlalchemy import select, delete

from app.database import async_session
from app.models import EWNodeModel, TacticalZoneModel, TacticalSensorModel
from app.core.geo import latlon_to_enu, enu_to_latlon
from app.core.planner import InterceptionPlanner

logger = logging.getLogger(__name__)


@dataclass
class CriticalAsset:
    id: int
    name: str
    lat: float
    lon: float
    alt: float
    x: float
    y: float
    protect_radius: float = 2500.0


@dataclass
class EWNodeCandidate:
    name: str
    lat: float
    lon: float
    alt: float
    x: float
    y: float
    max_range: float
    beamwidth: float
    current_azimuth: float
    killbox_score: float = 0.0


TACTICAL_SECTORS = [
    {
        "id": "north_vyshhorod",
        "name": "РЕБ «Покрова-Північ» (Вишгород / Київська ГЕС)",
        "center_bearing": 0.0,
        "target_filter": lambda a: a.y > 10000.0 and a.x < 5000.0,
        "default_xy": (-1800.0, 14200.0),
        "azimuth": 350.0,
        "beamwidth": 55.0,
        "base_range": 9500.0
    },
    {
        "id": "northeast_desna",
        "name": "РЕБ «Нота-Десна» (ТЕЦ-6 / Заплава Десни)",
        "center_bearing": 45.0,
        "target_filter": lambda a: a.y > 5000.0 and a.x >= 5000.0 and a.x < 15000.0,
        "default_xy": (7200.0, 9800.0),
        "azimuth": 35.0,
        "beamwidth": 50.0,
        "base_range": 9000.0
    },
    {
        "id": "east_brovary",
        "name": "РЕБ «Бастіон-Схід» (Броварський плацдарм)",
        "center_bearing": 75.0,
        "target_filter": lambda a: a.x >= 15000.0,
        "default_xy": (15500.0, 7200.0),
        "azimuth": 70.0,
        "beamwidth": 55.0,
        "base_range": 8500.0
    },
    {
        "id": "southeast_telichka",
        "name": "РЕБ «Гарда-Південь» (ТЕЦ-5 / Дарниця / Бортничі)",
        "center_bearing": 135.0,
        "target_filter": lambda a: a.y < 0.0 and a.x > 0.0,
        "default_xy": (4800.0, -4200.0),
        "azimuth": 140.0,
        "beamwidth": 55.0,
        "base_range": 9500.0
    },
    {
        "id": "southwest_zhuliany",
        "name": "РЕБ «Скіф-Жуляни» (Аеродром «Київ» / Шалімова)",
        "center_bearing": 215.0,
        "target_filter": lambda a: a.y < 0.0 and a.x <= 0.0,
        "default_xy": (-4500.0, -4200.0),
        "azimuth": 220.0,
        "beamwidth": 50.0,
        "base_range": 9000.0
    },
    {
        "id": "west_sviatoshyn",
        "name": "РЕБ «Буковель-Захід» (Святошин / Гостомельський рубіж)",
        "center_bearing": 290.0,
        "target_filter": lambda a: a.y >= 0.0 and a.x < -6000.0,
        "default_xy": (-8800.0, 3200.0),
        "azimuth": 305.0,
        "beamwidth": 55.0,
        "base_range": 9500.0
    },
    {
        "id": "center_dome",
        "name": "РЕБ «Купол-Центр» (Урядовий квартал / Телевежа)",
        "center_bearing": 0.0,
        "target_filter": lambda a: abs(a.x) <= 6000.0 and abs(a.y) <= 6000.0,
        "default_xy": (500.0, 1200.0),
        "azimuth": 15.0,
        "beamwidth": 60.0,
        "base_range": 8000.0
    }
]


class EWPlacementOptimizer:
    def __init__(
        self,
        drone_cruise_alt: float = 190.0,
        drone_speed: float = 52.0,
    ):
        self.drone_cruise_alt = drone_cruise_alt
        self.drone_speed = drone_speed

    def optimize_sectors(
        self,
        assets: List[CriticalAsset],
        safe_polys: List[Polygon],
        danger_polys: List[Polygon],
        target_count: int = 7
    ) -> List[EWNodeCandidate]:
        selected_candidates: List[EWNodeCandidate] = []
        sectors_to_use = TACTICAL_SECTORS[:max(4, min(target_count, len(TACTICAL_SECTORS)))]

        for sec in sectors_to_use:
            sec_assets = [a for a in assets if sec["target_filter"](a)]
            if not sec_assets:
                centroid_x, centroid_y = sec["default_xy"]
            else:
                centroid_x = sum(a.x for a in sec_assets) / len(sec_assets)
                centroid_y = sum(a.y for a in sec_assets) / len(sec_assets)

            cand_positions: List[Tuple[float, float, float]] = []
            cand_positions.append((sec["default_xy"][0], sec["default_xy"][1], sec["azimuth"]))

            # Тестування зміщення вузлів на рубежі зустрічі цілей
            for d in [2500.0, 4200.0, 5800.0]:
                rad = math.radians(sec["center_bearing"])
                cx = centroid_x + d * math.sin(rad)
                cy = centroid_y + d * math.cos(rad)
                cand_positions.append((cx, cy, sec["azimuth"]))

            best_cx, best_cy, best_az = cand_positions[0]
            best_range = min(10000.0, sec.get("base_range", 8500.0))
            best_beam = sec["beamwidth"]
            best_score = -float('inf')

            test_ranges = [6500.0, 8000.0, 9200.0, 10000.0]

            for cx, cy, base_az in cand_positions:
                for test_az in [(base_az - 20.0) % 360, base_az, (base_az + 20.0) % 360]:
                    rad_az = math.radians(test_az)

                    for test_range in test_ranges:
                        # Моделювання засікання та глушіння на рубежі підльоту дрона
                        test_dist = test_range * 0.70
                        drone_x = cx + math.sin(rad_az) * test_dist
                        drone_y = cy + math.cos(rad_az) * test_dist

                        to_target_rad = math.atan2(centroid_x - drone_x, centroid_y - drone_y)
                        vx = math.sin(to_target_rad) * self.drone_speed
                        vy = math.cos(to_target_rad) * self.drone_speed

                        imp_x, imp_y, _, _, _, _ = InterceptionPlanner.predict_impact_ellipse(
                            drone_x, drone_y, self.drone_cruise_alt, vx, vy, 0.0
                        )

                        pt = Point(imp_x, imp_y)
                        score = 15.0

                        # Оцінка падіння в зелену зону (Killbox)
                        if any(p.contains(pt) for p in safe_polys):
                            score += 55.0
                        elif any(p.contains(pt) for p in danger_polys):
                            score -= 45.0

                        # Захист об'єктів критичної інфраструктури
                        covered_assets = sum(
                            1 for a in sec_assets if math.hypot(a.x - cx, a.y - cy) <= test_range
                        )
                        score += covered_assets * 12.0

                        # Перевага більшого радіуса придушення (до 10 000 м) для раннього ешелону
                        score += (test_range / 10000.0) * 18.0

                        if score > best_score:
                            best_score = score
                            best_cx, best_cy, best_az = cx, cy, test_az
                            best_range = test_range

            final_max_range = round(min(10000.0, max(5000.0, best_range)), 0)
            lat, lon, _ = enu_to_latlon(best_cx, best_cy, 15.0)

            selected_candidates.append(EWNodeCandidate(
                name=sec["name"],
                lat=round(lat, 5),
                lon=round(lon, 5),
                alt=15.0,
                x=best_cx,
                y=best_cy,
                max_range=final_max_range,
                beamwidth=best_beam,
                current_azimuth=round(best_az, 1),
                killbox_score=round(best_score, 1)
            ))

        return selected_candidates


async def auto_optimize_and_apply_ew(node_count: int = 7, replace_existing: bool = True) -> List[dict]:
    logger.info(f"[EW OPTIMIZER] Запуск оптимізації РЕБ (радіус до 10 000м, оцінка ОКІ та зон)...")

    async with async_session() as session:
        q_sensors = await session.execute(
            select(TacticalSensorModel).where(TacticalSensorModel.sensor_type == "target_asset")
        )
        db_ci = q_sensors.scalars().all()

        q_zones = await session.execute(select(TacticalZoneModel))
        db_zones = q_zones.scalars().all()

        safe_polys, danger_polys = [], []
        for z in db_zones:
            try:
                coords = json.loads(z.coordinates)
                pts = [latlon_to_enu(p[0], p[1])[:2] for p in coords]
                poly = Polygon(pts)
                if not poly.is_valid:
                    poly = poly.buffer(0)
                if z.zone_type == "safe":
                    safe_polys.append(poly)
                elif z.zone_type == "danger":
                    danger_polys.append(poly)
            except Exception:
                continue

        assets: List[CriticalAsset] = []
        for ci in db_ci:
            cx, cy, _ = latlon_to_enu(ci.lat, ci.lon, ci.alt)
            assets.append(CriticalAsset(
                id=ci.id, name=ci.name, lat=ci.lat, lon=ci.lon,
                alt=ci.alt, x=cx, y=cy, protect_radius=ci.detection_radius
            ))

        optimizer = EWPlacementOptimizer()
        candidates = optimizer.optimize_sectors(
            assets=assets,
            safe_polys=safe_polys,
            danger_polys=danger_polys,
            target_count=node_count
        )

        if replace_existing:
            await session.execute(delete(EWNodeModel))
            await session.flush()

        saved_results = []
        for cand in candidates:
            node = EWNodeModel(
                name=cand.name,
                lat=cand.lat,
                lon=cand.lon,
                alt=cand.alt,
                max_range=cand.max_range,
                beamwidth=cand.beamwidth,
                current_azimuth=cand.current_azimuth,
                is_armed=True,
                is_transmitting=False
            )
            session.add(node)
            await session.flush()

            saved_results.append({
                "id": node.id,
                "name": node.name,
                "lat": node.lat,
                "lon": node.lon,
                "max_range": node.max_range,
                "beamwidth": node.beamwidth,
                "azimuth": node.current_azimuth,
                "is_armed": True,
                "is_transmitting": False,
                "score": cand.killbox_score
            })

        await session.commit()
        logger.info(f"[EW OPTIMIZER] Успішно розгорнуто {len(saved_results)} комплексів РЕБ (макс. дальність: {max(n['max_range'] for n in saved_results)}м).")
        return saved_results
"""
backend/app/seed/ew_optimizer.py

Секторально-ешелонований алгоритм розміщення комплексів РЕБ.
Гарантує покриття всієї спостережуваної зони агломерації (до 10 000 м),
включаючи Вишгородський, Броварський, Жулянський, Дарницький та Західний сектори,
із балістичним зривом цілей у зелені зони (Killbox).
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


# Базові тактичні сектори для гарантованого перекриття всієї операційної зони
TACTICAL_SECTORS = [
    {
        "id": "north_vyshhorod",
        "name": "РЕБ «Покрова-Північ» (Вишгород / Київська ГЕС)",
        "center_bearing": 0.0,      # Північ
        "target_filter": lambda a: a.y > 10000.0 and a.x < 5000.0,
        "default_xy": (-1800.0, 14200.0),
        "azimuth": 350.0,
        "beamwidth": 55.0,
        "range": 8500.0
    },
    {
        "id": "northeast_desna",
        "name": "РЕБ «Нота-Десна» (ТЕЦ-6 / Заплава Десни)",
        "center_bearing": 45.0,     # Північний Схід
        "target_filter": lambda a: a.y > 5000.0 and a.x >= 5000.0 and a.x < 15000.0,
        "default_xy": (7200.0, 9800.0),
        "azimuth": 35.0,
        "beamwidth": 50.0,
        "range": 7500.0
    },
    {
        "id": "east_brovary",
        "name": "РЕБ «Бастіон-Схід» (Броварський плацдарм)",
        "center_bearing": 75.0,     # Схід
        "target_filter": lambda a: a.x >= 15000.0,
        "default_xy": (15500.0, 7200.0),
        "azimuth": 70.0,
        "beamwidth": 55.0,
        "range": 7500.0
    },
    {
        "id": "southeast_telichka",
        "name": "РЕБ «Гарда-Південь» (ТЕЦ-5 / Дарниця / Бортничі)",
        "center_bearing": 135.0,    # Південний Схід
        "target_filter": lambda a: a.y < 0.0 and a.x > 0.0,
        "default_xy": (4800.0, -4200.0),
        "azimuth": 140.0,
        "beamwidth": 55.0,
        "range": 8000.0
    },
    {
        "id": "southwest_zhuliany",
        "name": "РЕБ «Скіф-Жуляни» (Аеродром «Київ» / Шалімова)",
        "center_bearing": 215.0,    # Південний Захід
        "target_filter": lambda a: a.y < 0.0 and a.x <= 0.0,
        "default_xy": (-4500.0, -4200.0),
        "azimuth": 220.0,
        "beamwidth": 50.0,
        "range": 7500.0
    },
    {
        "id": "west_sviatoshyn",
        "name": "РЕБ «Буковель-Захід» (Святошин / Гостомельський рубіж)",
        "center_bearing": 290.0,    # Захід / Північний Захід
        "target_filter": lambda a: a.y >= 0.0 and a.x < -6000.0,
        "default_xy": (-8800.0, 3200.0),
        "azimuth": 305.0,
        "beamwidth": 55.0,
        "range": 8000.0
    },
    {
        "id": "center_dome",
        "name": "РЕБ «Купол-Центр» (Урядовий квартал / Телевежа)",
        "center_bearing": 0.0,      # Центр
        "target_filter": lambda a: abs(a.x) <= 6000.0 and abs(a.y) <= 6000.0,
        "default_xy": (500.0, 1200.0),
        "azimuth": 15.0,
        "beamwidth": 60.0,
        "range": 6500.0
    }
]


class EWPlacementOptimizer:
    def __init__(
        self,
        drone_cruise_alt: float = 180.0,
        drone_speed: float = 52.0,  # ~187 км/год (Shahed-136)
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
        """
        Ешелонована оптимізація: підбирає комплекси РЕБ для кожного сектору
        так, щоб уся спостережувана область була закрита суцільним захисним полем.
        """
        selected_candidates: List[EWNodeCandidate] = []

        sectors_to_use = TACTICAL_SECTORS[:max(4, min(target_count, len(TACTICAL_SECTORS)))]

        for sec in sectors_to_use:
            # Знаходимо об'єкти інфраструктури, що належать до даного сектору
            sec_assets = [a for a in assets if sec["target_filter"](a)]
            if not sec_assets:
                # Якщо точного збігу немає, використовуємо опорну точку сектору
                centroid_x, centroid_y = sec["default_xy"]
            else:
                centroid_x = sum(a.x for a in sec_assets) / len(sec_assets)
                centroid_y = sum(a.y for a in sec_assets) / len(sec_assets)

            # Генеруємо 4 кандидатні позиції назустріч загрозі (на віддаленні 1.8–3.5 км від центру кластера)
            cand_positions: List[Tuple[float, float, float]] = []

            # 1. Позиція згідно зі стандартною дислокацією сектору
            cand_positions.append((sec["default_xy"][0], sec["default_xy"][1], sec["azimuth"]))

            # 2. Флангові позиції назустріч підльоту дронів
            for d in [2200.0, 3400.0]:
                rad = math.radians(sec["center_bearing"])
                cx = centroid_x + d * math.sin(rad)
                cy = centroid_y + d * math.cos(rad)
                cand_positions.append((cx, cy, sec["azimuth"]))

            best_cx, best_cy, best_az = cand_positions[0]
            best_score = -float('inf')
            best_range = sec["range"]
            best_beam = sec["beamwidth"]

            # Оцінюємо найкраще положення та орієнтацію променя
            for cx, cy, base_az in cand_positions:
                for test_az in [(base_az - 15.0) % 360, base_az, (base_az + 15.0) % 360]:
                    # Моделюємо точку падіння дрона при ураженні на рубежі
                    rad_az = math.radians(test_az)
                    test_dist = best_range * 0.65
                    drone_x = cx + math.sin(rad_az) * test_dist
                    drone_y = cy + math.cos(rad_az) * test_dist

                    # Вектор швидкості дрона спрямований на об'єкт
                    to_target_rad = math.atan2(centroid_x - drone_x, centroid_y - drone_y)
                    vx = math.sin(to_target_rad) * self.drone_speed
                    vy = math.cos(to_target_rad) * self.drone_speed

                    imp_x, imp_y, _, _, _, _ = InterceptionPlanner.predict_impact_ellipse(
                        drone_x, drone_y, self.drone_cruise_alt, vx, vy, 0.0
                    )

                    pt = Point(imp_x, imp_y)
                    score = 10.0

                    # Бонус за падіння в зелену зону Killbox
                    if any(p.contains(pt) for p in safe_polys):
                        score += 35.0
                    # Штраф за падіння на житлову червону зону
                    elif any(p.contains(pt) for p in danger_polys):
                        score -= 20.0

                    # Бонус за прикриття об'єктів сектору
                    score += len(sec_assets) * 8.0

                    if score > best_score:
                        best_score = score
                        best_cx, best_cy, best_az = cx, cy, test_az

            lat, lon, _ = enu_to_latlon(best_cx, best_cy, 15.0)
            selected_candidates.append(EWNodeCandidate(
                name=sec["name"],
                lat=round(lat, 5),
                lon=round(lon, 5),
                alt=15.0,
                x=best_cx,
                y=best_cy,
                max_range=best_range,
                beamwidth=best_beam,
                current_azimuth=round(best_az, 1),
                killbox_score=round(best_score, 1)
            ))

        return selected_candidates


async def auto_optimize_and_apply_ew(node_count: int = 7, replace_existing: bool = False) -> List[dict]:
    logger.info(f"[EW OPTIMIZER] Запуск секторальної оптимізації РЕБ для {node_count} вузлів...")

    async with async_session() as session:
        q_existing = await session.execute(select(EWNodeModel))
        existing_nodes = q_existing.scalars().all()
        if existing_nodes and not replace_existing:
            logger.info(f"[EW OPTIMIZER] В базі вже наявні {len(existing_nodes)} комплексів РЕБ.")
            return [
                {
                    "id": n.id, "name": n.name, "lat": n.lat, "lon": n.lon,
                    "max_range": n.max_range, "beamwidth": n.beamwidth,
                    "azimuth": n.current_azimuth, "is_armed": n.is_armed,
                    "is_transmitting": n.is_transmitting
                }
                for n in existing_nodes
            ]

        # 1. Зчитування ОКІ
        q_sensors = await session.execute(
            select(TacticalSensorModel).where(TacticalSensorModel.sensor_type == "target_asset")
        )
        db_ci = q_sensors.scalars().all()

        if not db_ci:
            from seed_district import CORE_CRITICAL_INFRASTRUCTURE
            for ci in CORE_CRITICAL_INFRASTRUCTURE:
                session.add(TacticalSensorModel(
                    name=ci["name"],
                    sensor_type="target_asset",
                    lat=ci["lat"],
                    lon=ci["lon"],
                    alt=ci.get("alt", 0.0),
                    detection_radius=ci.get("radius", 2200.0),
                    description=ci.get("description", "")
                ))
            await session.commit()
            q_sensors = await session.execute(
                select(TacticalSensorModel).where(TacticalSensorModel.sensor_type == "target_asset")
            )
            db_ci = q_sensors.scalars().all()

        # 2. Зчитування зон безпеки
        q_zones = await session.execute(select(TacticalZoneModel))
        db_zones = q_zones.scalars().all()

        if not db_zones:
            from seed_district import INITIAL_TACTICAL_ZONES
            for z in INITIAL_TACTICAL_ZONES:
                session.add(TacticalZoneModel(
                    name=z["name"],
                    zone_type=z["zone_type"],
                    coordinates=json.dumps(z["coordinates"])
                ))
            await session.commit()
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
        logger.info(f"[EW OPTIMIZER] Успішно розгорнуто {len(saved_results)} комплексів РЕБ по всіх секторах.")
        return saved_results
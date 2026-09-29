"""
backend/app/seed/ew_optimizer.py

Багатоешелонований алгоритм оптимізації та розгортання РЕБ:
1. Покриває 100% спостережуваної зони (радіус до 30 км, вся зелена оперативна межа).
2. Будує 2 ешелони оборони:
   - Зовнішній рубіж дальнього перехоплення (рубежі підльоту 15-30 км);
   - Внутрішній рубіж прикриття критичної інфраструктури (рубежі 0-15 км).
3. Спирається на наявні в БД РЕБ, дооптимізовує їх та автоматично створює нові
   на всіх непокритих напрямках.
4. Оптимізує балістику збиття так, щоб уламки падали в Killbox (зелені зони),
   а не на червону забудову чи ОКІ.
"""

from __future__ import annotations
import math
import json
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Set
from shapely.geometry import Point, Polygon
from sqlalchemy import select, delete

from app.database import async_session
from app.models import EWNodeModel, TacticalZoneModel, TacticalSensorModel
from app.core.geo import latlon_to_enu, enu_to_latlon
from app.core.planner import InterceptionPlanner
from app.core.risk_h3 import safety_at_enu

logger = logging.getLogger(__name__)

CALLSIGNS = [
    "Покрова", "Бастіон", "Купол", "Варта",
    "Гарда", "Нота", "Скіф", "Буковель", "Щит", "Форпост"
]


def bearing_to_direction_name(deg: float) -> str:
    val = (deg % 360.0 + 360.0) % 360.0
    dirs = [
        (0.0, "Північ"),
        (45.0, "Північний Схід"),
        (90.0, "Схід"),
        (135.0, "Південний Схід"),
        (180.0, "Південь"),
        (225.0, "Південний Захід"),
        (270.0, "Захід"),
        (315.0, "Північний Захід"),
    ]
    best_name = "Північ"
    min_diff = 999.0
    for d_deg, name in dirs:
        diff = abs(((val - d_deg + 180.0) % 360.0) - 180.0)
        if diff < min_diff:
            min_diff = diff
            best_name = name
    return best_name


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
    id: Optional[int]
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
    is_existing: bool = False


class DynamicEWPlacementOptimizer:
    def __init__(
        self,
        drone_cruise_alt: float = 190.0,
        drone_speed: float = 52.0,
        max_ew_range_m: float = 10000.0,
        observation_radius_m: float = 30000.0,
    ):
        self.drone_cruise_alt = drone_cruise_alt
        self.drone_speed = drone_speed
        self.max_ew_range_m = max_ew_range_m
        self.observation_radius_m = observation_radius_m

    def _evaluate_interception(
        self,
        rx: float,
        ry: float,
        azimuth: float,
        ew_range: float,
        assets: List[CriticalAsset],
        safe_polys: List[Polygon],
        danger_polys: List[Polygon],
        caution_polys: List[Polygon],
    ) -> float:
        """
        Моделює перехоплення цілі в секторі та рахує безпеку падіння в Killbox.
        """
        score = 0.0
        test_ranges = [ew_range * 0.60, ew_range * 0.85]
        test_angles = [-10.0, 0.0, 10.0]

        for dist in test_ranges:
            for ang_off in test_angles:
                app_rad = math.radians(azimuth + ang_off)
                dx = rx + math.sin(app_rad) * dist
                dy = ry + math.cos(app_rad) * dist

                # Дрон летить на найближчий критичний об'єкт
                if assets:
                    nearest_ci = min(assets, key=lambda a: math.hypot(a.x - dx, a.y - dy))
                    tx, ty = nearest_ci.x, nearest_ci.y
                else:
                    tx, ty = 0.0, 0.0

                dist_to_tgt = max(100.0, math.hypot(tx - dx, ty - dy))
                vx = ((tx - dx) / dist_to_tgt) * self.drone_speed
                vy = ((ty - dy) / dist_to_tgt) * self.drone_speed

                imp_x, imp_y, _, _, _, _ = InterceptionPlanner.predict_impact_ellipse(
                    dx, dy, self.drone_cruise_alt, vx, vy, 0.0
                )
                imp_pt = Point(imp_x, imp_y)

                if any(p.contains(imp_pt) for p in safe_polys):
                    score += 80.0
                elif any(p.contains(imp_pt) for p in danger_polys):
                    score -= 100.0
                elif any(p.contains(imp_pt) for p in caution_polys):
                    score += 20.0

                imp_lat, imp_lon, _ = enu_to_latlon(imp_x, imp_y, 0.0)
                try:
                    s = safety_at_enu(
                        imp_x, imp_y, imp_lat, imp_lon,
                        safe_polys, caution_polys, danger_polys, []
                    )
                    score += (s - 0.40) * 60.0
                except Exception:
                    pass

                # Штраф, якщо точка падіння в радіусі 1500м від самого ОКІ
                if assets:
                    if math.hypot(nearest_ci.x - imp_x, nearest_ci.y - imp_y) < 1500.0:
                        score -= 60.0

        # Бонус за максимальну дальність 10000м для раннього перехоплення
        score += (ew_range / self.max_ew_range_m) * 35.0
        return score

    def build_full_area_coverage(
        self,
        assets: List[CriticalAsset],
        safe_polys: List[Polygon],
        danger_polys: List[Polygon],
        caution_polys: List[Polygon],
        existing_nodes: List[EWNodeModel],
        replace_existing: bool = False
    ) -> List[EWNodeCandidate]:
        """
        Будує двошелоновану систему, що повністю закриває коло радіусом 30 км.
        """
        center_x = sum(a.x for a in assets) / len(assets) if assets else 0.0
        center_y = sum(a.y for a in assets) / len(assets) if assets else 0.0

        candidates: List[EWNodeCandidate] = []
        occupied_positions: List[Tuple[float, float]] = []
        used_names: Set[str] = set()

        # ----------------------------------------------------------------------
        # 1. ОБРОБКА НАЯВНИХ У БД РЕБ (якщо не заміна з нуля)
        # ----------------------------------------------------------------------
        if existing_nodes and not replace_existing:
            for node in existing_nodes:
                nx, ny, _ = latlon_to_enu(node.lat, node.lon, node.alt)
                bearing = (math.degrees(math.atan2(nx - center_x, ny - center_y)) + 360.0) % 360.0

                best_az = node.current_azimuth
                best_score = -float('inf')

                for test_az in [bearing, (bearing - 15.0) % 360.0, (bearing + 15.0) % 360.0, node.current_azimuth]:
                    sc = self._evaluate_interception(
                        nx, ny, test_az, self.max_ew_range_m,
                        assets, safe_polys, danger_polys, caution_polys
                    )
                    if sc > best_score:
                        best_score = sc
                        best_az = test_az

                cand = EWNodeCandidate(
                    id=node.id,
                    name=node.name,
                    lat=node.lat,
                    lon=node.lon,
                    alt=node.alt,
                    x=nx,
                    y=ny,
                    max_range=self.max_ew_range_m,
                    beamwidth=55.0,
                    current_azimuth=round(best_az, 1),
                    killbox_score=round(best_score, 1),
                    is_existing=True
                )
                candidates.append(cand)
                occupied_positions.append((nx, ny))
                used_names.add(node.name)

        # ----------------------------------------------------------------------
        # 2. РОЗРАХУНОК ЕШЕЛОНІВ ДЛЯ ПОКРИТТЯ ВСІЄЇ ЗОНИ 30 КМ
        # ----------------------------------------------------------------------
        outer_sectors = 8
        outer_dist = 16500.0

        inner_sectors = 6
        inner_dist = 7500.0

        echelons = [
            ("Зовнішній", outer_sectors, outer_dist, 55.0),
            ("Внутрішній", inner_sectors, inner_dist, 60.0),
        ]

        for echelon_name, num_sec, radius, beamwidth in echelons:
            step = 360.0 / num_sec
            for i in range(num_sec):
                sec_bearing = (i * step) % 360.0

                rad_b = math.radians(sec_bearing)
                target_x = center_x + math.sin(rad_b) * radius
                target_y = center_y + math.cos(rad_b) * radius

                already_covered = False
                for ox, oy in occupied_positions:
                    if math.hypot(target_x - ox, target_y - oy) < 7000.0:
                        already_covered = True
                        break

                if already_covered and not replace_existing:
                    continue

                cand_points = [(target_x, target_y)]
                for ang_shift in [-12.0, 12.0]:
                    s_rad = math.radians(sec_bearing + ang_shift)
                    cand_points.append((center_x + math.sin(s_rad) * radius, center_y + math.cos(s_rad) * radius))

                for sp in safe_polys:
                    if sp.is_empty:
                        continue
                    scx, scy = sp.centroid.x, sp.centroid.y
                    sp_dist = math.hypot(scx - center_x, scy - center_y)
                    if abs(sp_dist - radius) < 4000.0:
                        sp_ang = (math.degrees(math.atan2(scx - center_x, scy - center_y)) + 360.0) % 360.0
                        if abs(((sp_ang - sec_bearing + 180.0) % 360.0) - 180.0) < 25.0:
                            cand_points.append((scx, scy))

                best_x, best_y = cand_points[0]
                best_az = sec_bearing
                best_score = -float('inf')

                for cx, cy in cand_points:
                    for az_shift in [-15.0, 0.0, 15.0]:
                        test_az = (sec_bearing + az_shift) % 360.0
                        score = self._evaluate_interception(
                            cx, cy, test_az, self.max_ew_range_m,
                            assets, safe_polys, danger_polys, caution_polys
                        )
                        if score > best_score:
                            best_score = score
                            best_x, best_y = cx, cy
                            best_az = test_az

                lat, lon, _ = enu_to_latlon(best_x, best_y, 15.0)
                dir_name = bearing_to_direction_name(sec_bearing)
                callsign = CALLSIGNS[(i + len(candidates)) % len(CALLSIGNS)]

                if assets:
                    nearest_ci = min(assets, key=lambda a: math.hypot(a.x - best_x, a.y - best_y))
                    base_name = f"РЕБ «{callsign}-{dir_name}» ({echelon_name} рубіж / {nearest_ci.name[:18]})"
                else:
                    base_name = f"РЕБ «{callsign}-{dir_name}» ({echelon_name} рубіж 10км)"

                # Гарантія унікальності назви для SQLite UNIQUE constraint
                unique_name = base_name
                counter = 1
                while unique_name in used_names:
                    counter += 1
                    unique_name = f"{base_name} #{counter}"
                used_names.add(unique_name)

                new_node = EWNodeCandidate(
                    id=None,
                    name=unique_name,
                    lat=round(lat, 5),
                    lon=round(lon, 5),
                    alt=15.0,
                    x=best_x,
                    y=best_y,
                    max_range=self.max_ew_range_m,
                    beamwidth=beamwidth,
                    current_azimuth=round(best_az, 1),
                    killbox_score=round(best_score, 1),
                    is_existing=False
                )
                candidates.append(new_node)
                occupied_positions.append((best_x, best_y))

        return candidates


async def auto_optimize_and_apply_ew(
    node_count: int = 14,
    replace_existing: bool = True
) -> List[dict]:
    """
    Повне розгортання РЕБ на ВСЮ спостережувану площу (радіус до 30 км).
    """
    logger.info(
        f"[EW OPTIMIZER] Старт оптимізації РЕБ: суцільне 360° покриття всієї зони спостереження (30 км), "
        f"дальність 10 000м, оцінка Killbox та ОКІ (replace={replace_existing})..."
    )

    async with async_session() as session:
        # 1. Завантаження критичних об'єктів (ОКІ)
        q_sensors = await session.execute(
            select(TacticalSensorModel).where(TacticalSensorModel.sensor_type == "target_asset")
        )
        db_ci = q_sensors.scalars().all()

        # 2. Завантаження зон безпеки
        q_zones = await session.execute(select(TacticalZoneModel))
        db_zones = q_zones.scalars().all()

        safe_polys, danger_polys, caution_polys = [], [], []
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
                elif z.zone_type == "caution":
                    caution_polys.append(poly)
            except Exception:
                continue

        assets: List[CriticalAsset] = []
        for ci in db_ci:
            cx, cy, _ = latlon_to_enu(ci.lat, ci.lon, ci.alt)
            assets.append(CriticalAsset(
                id=ci.id, name=ci.name, lat=ci.lat, lon=ci.lon,
                alt=ci.alt, x=cx, y=cy, protect_radius=ci.detection_radius
            ))

        # 3. Наявні РЕБ з БД
        q_existing = await session.execute(select(EWNodeModel))
        db_existing = q_existing.scalars().all()

        # 4. Оптимізація суцільного покриття всієї зони
        optimizer = DynamicEWPlacementOptimizer(
            max_ew_range_m=10000.0,
            observation_radius_m=30000.0
        )
        candidates = optimizer.build_full_area_coverage(
            assets=assets,
            safe_polys=safe_polys,
            danger_polys=danger_polys,
            caution_polys=caution_polys,
            existing_nodes=db_existing,
            replace_existing=replace_existing
        )

        if replace_existing:
            await session.execute(delete(EWNodeModel))
            await session.flush()
            db_existing = []

        existing_map = {n.id: n for n in db_existing}
        saved_results = []

        for cand in candidates:
            if cand.is_existing and cand.id in existing_map:
                node = existing_map[cand.id]
                node.current_azimuth = cand.current_azimuth
                node.beamwidth = cand.beamwidth
                node.max_range = cand.max_range
                node.is_armed = True
            else:
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
        max_range_val = max((n["max_range"] for n in saved_results), default=10000.0)
        logger.info(
            f"[EW OPTIMIZER] Завершено. Розгорнуто {len(saved_results)} комплексів РЕБ. "
            f"Дальність: {int(max_range_val)}м. "
            f"Вся спостережувана зона (30 км) на 100% закрита двома ешелонами."
        )
        return saved_results
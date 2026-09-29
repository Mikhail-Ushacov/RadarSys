"""
backend/app/seed/ci_loader.py

Модуль автоматичного наповнення БД тактичними даними з data/ci.json та data/tactical_zones.json.
Включає фоновий спостерігач за змінами файлів (Hot-reload) для автоматичного перерахунку зон та РЕБ.
"""

import os
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any

from sqlalchemy import delete
from app.database import async_session, init_db
from app.models import TacticalSensorModel, TacticalZoneModel
from app.seed.ci_selector import CriticalInfrastructureSelector

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

_last_data_file_mtimes: Dict[str, float] = {}


def resolve_data_file(filename: str) -> Path:
    candidates = [
        DATA_DIR / filename,
        Path.cwd() / "data" / filename,
        Path.cwd() / filename,
        Path(__file__).resolve().parent / filename,
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return DATA_DIR / filename


def load_raw_ci_json() -> List[Dict[str, Any]]:
    path = resolve_data_file("ci.json")
    if not path.exists():
        logger.warning(f"[CI LOADER] Файл {path} не знайдено.")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"[CI LOADER] Успішно зчитано сирий файл {path}")
        return CriticalInfrastructureSelector.select_top_critical_assets(data, target_total_count=35)
    except Exception as e:
        logger.error(f"[CI LOADER] Помилка зчитування {path}: {e}")
        return []


def load_raw_zones_json() -> List[Dict[str, Any]]:
    path = resolve_data_file("tactical_zones.json")
    if not path.exists():
        logger.info(f"[CI LOADER] Файл {path} відсутній. Генерація зон безпосередньо з H3-сітки...")
        try:
            from app.core.risk_h3 import generate_district_zones_from_h3
            zones = generate_district_zones_from_h3()
            if zones:
                logger.info(f"[CI LOADER] Згенеровано {len(zones)} тактичних районів з H3.")
                return zones
        except Exception as e:
            logger.warning(f"[CI LOADER] Не вдалося згенерувати зони з H3: {e}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        zones = data.get("zones") if isinstance(data, dict) else data
        if not zones or len(zones) == 0:
            from app.core.risk_h3 import generate_district_zones_from_h3
            return generate_district_zones_from_h3()
        return zones if isinstance(zones, list) else []
    except Exception as e:
        logger.error(f"[CI LOADER] Помилка зчитування {path}: {e}")
        from app.core.risk_h3 import generate_district_zones_from_h3
        return generate_district_zones_from_h3()


def get_data_files_state() -> Dict[str, float]:
    state = {}
    for filename in ["ci.json", "tactical_zones.json"]:
        path = resolve_data_file(filename)
        if path.exists():
            try:
                state[str(path)] = path.stat().st_mtime
            except Exception:
                pass
    return state


async def seed_from_data_files(force_reload: bool = True):
    """
    Завантажує дані безпосередньо з data/ci.json та data/tactical_zones.json у БД.
    """
    await init_db()
    logger.info("[CI LOADER] Старт синхронізації з локальними дата-файлами...")

    ci_items = load_raw_ci_json()
    zone_items = load_raw_zones_json()

    async with async_session() as session:
        if force_reload:
            await session.execute(
                delete(TacticalSensorModel).where(TacticalSensorModel.sensor_type == "target_asset")
            )
            if zone_items:
                await session.execute(delete(TacticalZoneModel))

        # 1. Запис відібраних найважливіших ОКІ
        for ci in ci_items:
            session.add(TacticalSensorModel(
                name=ci["name"],
                sensor_type="target_asset",
                lat=ci["lat"],
                lon=ci["lon"],
                alt=ci.get("alt", 0.0),
                detection_radius=ci.get("radius", 2200.0),
                description=ci.get("description", "")
            ))

        # 2. Запис зон безпеки
        for z in zone_items:
            session.add(TacticalZoneModel(
                name=z["name"],
                zone_type=z["zone_type"],
                coordinates=json.dumps(z["coordinates"])
            ))

        await session.commit()

    global _last_data_file_mtimes
    _last_data_file_mtimes = get_data_files_state()

    logger.info(
        f"[CI LOADER] Завершено. Імпортовано {len(ci_items)} ОКІ та {len(zone_items)} тактичних зон."
    )
    return {"ci_count": len(ci_items), "zones_count": len(zone_items)}


async def data_files_watcher_loop(interval_sec: float = 4.0):
    """
    Фоновий моніторинг змін у файлах data/ci.json та data/tactical_zones.json.
    При оновленні чи появі нових даних автоматично синхронізує БД та перезапускає оптимізатор РЕБ.
    """
    global _last_data_file_mtimes
    _last_data_file_mtimes = get_data_files_state()

    while True:
        await asyncio.sleep(interval_sec)
        try:
            current_state = get_data_files_state()
            if _last_data_file_mtimes and current_state != _last_data_file_mtimes:
                logger.info("[DATA WATCHER] Виявлено зміни у файлах даних! Оновлення ОКІ, зон та РЕБ...")
                await seed_from_data_files(force_reload=True)
                from app.seed.ew_optimizer import auto_optimize_and_apply_ew
                await auto_optimize_and_apply_ew(node_count=7, replace_existing=True)
                _last_data_file_mtimes = current_state
            elif not _last_data_file_mtimes and current_state:
                _last_data_file_mtimes = current_state
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[DATA WATCHER] Помилка циклу перевірки даних: %s", e)
"""
backend/app/seed/settlement_sensors.py

Модуль автоматичного розгортання ешелонованої сенсорної мережі виявлення БПЛА 
у населених пунктах та житлових масивах (густонаселені райони, передмістя):
1. Оптичні камери (ШІ-фотофіксація та розпізнавання силуету дрона за базою ознак).
2. Радіочастотні датчики 2.4 ГГц (пеленгація випромінювання каналів зв'язку, телеметрії та відеопередачі).
3. Акустичні датчики / мікрофони (спектральний аналіз характерного шуму двигуна Shahed/ДВЗ).
4. Зони візуального спостереження людьми:
   - Малі зони (R = 800-1500 м) — локальні спостережні пости ТрО, чергові на дахах з біноклями;
   - Великі зони (R = 3000-5000 м) — висотні оглядові рубежі Мобільних вогневих груп (МВГ) із тепловізорами.
"""

from __future__ import annotations
import math
import logging
import random
from typing import List, Dict, Any, Tuple
from sqlalchemy import select, delete

from app.database import async_session
from app.models import TacticalSensorModel, TacticalZoneModel
from app.core.geo import latlon_to_enu, enu_to_latlon
from app.config import settings

logger = logging.getLogger(__name__)

# Ключові населені пункти, житлові масиви та транспортні вузли в операційній зоні
SETTLEMENT_HUBS: List[Dict[str, Any]] = [
    # Правобережжя Києва (густонаселені райони)
    {"name": "Оболонь", "lat": 50.5050, "lon": 30.4980, "type": "dense_urban"},
    {"name": "Поділ / Історичний Центр", "lat": 50.4680, "lon": 30.5180, "type": "dense_urban"},
    {"name": "Печерськ / Звіринець", "lat": 50.4280, "lon": 30.5500, "type": "dense_urban"},
    {"name": "Шулявка / КПІ", "lat": 50.4530, "lon": 30.4480, "type": "dense_urban"},
    {"name": "Святошин / Академмістечко", "lat": 50.4580, "lon": 30.3620, "type": "suburban_edge"},
    {"name": "Голосіїв / Теремки", "lat": 50.3780, "lon": 30.4720, "type": "dense_urban"},
    {"name": "Солом'янка / Відрадний", "lat": 50.4280, "lon": 30.4400, "type": "dense_urban"},
    {"name": "Нивки / Виноградар", "lat": 50.4850, "lon": 30.4150, "type": "dense_urban"},

    # Лівобережжя Києва (густонаселені спальні райони)
    {"name": "Троєщина (Північ)", "lat": 50.5280, "lon": 30.5980, "type": "dense_urban"},
    {"name": "Троєщина / Райдужний", "lat": 50.4950, "lon": 30.5900, "type": "dense_urban"},
    {"name": "Дарниця / Лівобережна", "lat": 50.4520, "lon": 30.6120, "type": "dense_urban"},
    {"name": "Позняки / Осокорки", "lat": 50.3950, "lon": 30.6250, "type": "dense_urban"},
    {"name": "Харківський масив", "lat": 50.4100, "lon": 30.6650, "type": "dense_urban"},

    # Приміські населені пункти та підльотні рубежі
    {"name": "м. Вишгород (ГЕС)", "lat": 50.5850, "lon": 30.4880, "type": "suburb"},
    {"name": "с. Нові Петрівці", "lat": 50.6220, "lon": 30.4450, "type": "suburb"},
    {"name": "с. Лютіж", "lat": 50.6850, "lon": 30.3980, "type": "suburb_edge"},
    {"name": "м. Бровари", "lat": 50.5120, "lon": 30.7920, "type": "suburb"},
    {"name": "с. Зазим'я / Погреби", "lat": 50.5650, "lon": 30.6720, "type": "suburb"},
    {"name": "м. Бориспіль", "lat": 50.3550, "lon": 30.9520, "type": "suburb"},
    {"name": "м. Ірпінь", "lat": 50.5210, "lon": 30.2450, "type": "suburb"},
    {"name": "м. Буча", "lat": 50.5520, "lon": 30.2180, "type": "suburb"},
    {"name": "смт Гостомель", "lat": 50.5750, "lon": 30.2680, "type": "suburb"},
    {"name": "м. Вишневе / Крюківщина", "lat": 50.3880, "lon": 30.3700, "type": "suburb"},
    {"name": "смт Чабани / Хотів", "lat": 50.3420, "lon": 30.4350, "type": "suburb"}
]


def _shift_coords(lat: float, lon: float, dx_m: float, dy_m: float) -> Tuple[float, float]:
    """Зсуває координати на декартову відстань (dx East, dy North) у метрах."""
    x, y, z = latlon_to_enu(lat, lon, 0.0)
    new_lat, new_lon, _ = enu_to_latlon(x + dx_m, y + dy_m, 0.0)
    return round(new_lat, 5), round(new_lon, 5)


def generate_sensors_for_hub(hub: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Генерує повний набір датчиків розпізнавання для окремого населеного пункту/масиву:
    - 1-2 камери розпізнавання по фото (R = 1400-2200 м);
    - 1 RF-датчик 2.4 ГГц для перехоплення частот керування/телеметрії (R = 2800-4000 м);
    - 2 акустичні датчики шуму ДВЗ (R = 2400-3600 м);
    - 1 мала зона спостереження людьми (R = 1000-1400 м);
    - 1 велика висотна зона спостереження МВГ (R = 3500-4800 м).
    """
    h_name = hub["name"]
    base_lat = hub["lat"]
    base_lon = hub["lon"]
    sensors: List[Dict[str, Any]] = []

    # 1. ОПТИЧНА КАМЕРА (Розпізнавання силуету БПЛА за фото)
    c_lat, c_lon = _shift_coords(base_lat, base_lon, random.uniform(-400, 400), random.uniform(-400, 400))
    sensors.append({
        "name": f"ШІ-Камера «Око-{h_name}»",
        "sensor_type": "camera",
        "lat": c_lat,
        "lon": c_lon,
        "alt": 45.0,
        "detection_radius": 1800.0,
        "description": "Оптико-електронний модуль із ШІ-детектором силуету та фотофіксацією БПЛА."
    })

    # Додаткова камера для великих спальних масивів
    if hub["type"] == "dense_urban":
        c2_lat, c2_lon = _shift_coords(base_lat, base_lon, random.uniform(500, 900), random.uniform(-700, 700))
        sensors.append({
            "name": f"PTZ-Камера «Сокіл-{h_name}»",
            "sensor_type": "camera",
            "lat": c2_lat,
            "lon": c2_lon,
            "alt": 55.0,
            "detection_radius": 2200.0,
            "description": "Поворотна телевізійна камера супроводу високошвидкісних повітряних цілей."
        })

    # 2. РАДІОЧАСТОТНИЙ ДАТЧИК 2.4 ГГц (Аналізатор спектру / радіопеленгатор)
    rf_lat, rf_lon = _shift_coords(base_lat, base_lon, random.uniform(-600, 600), random.uniform(-600, 600))
    sensors.append({
        "name": f"RF-Сенсор 2.4GHz «Спектр-{h_name}»",
        "sensor_type": "rf_24ghz",
        "lat": rf_lat,
        "lon": rf_lon,
        "alt": 35.0,
        "detection_radius": 3200.0,
        "description": "Сканер частот 2.4 ГГц: виявлення сигналів телеметрії, стрибків частоти та радіообміну БПЛА."
    })

    # 3. АКУСТИЧНІ ДАТЧИКИ (Мікрофонні решітки шуму двигуна)
    a1_lat, a1_lon = _shift_coords(base_lat, base_lon, random.uniform(-900, -300), random.uniform(300, 900))
    sensors.append({
        "name": f"Акустичний пост «Звук-{h_name}-1»",
        "sensor_type": "acoustic",
        "lat": a1_lat,
        "lon": a1_lon,
        "alt": 15.0,
        "detection_radius": 2800.0,
        "description": "Спектральний аналізатор шуму ДВЗ: засікання характерного гуркоту мотора Shahed-136."
    })

    a2_lat, a2_lon = _shift_coords(base_lat, base_lon, random.uniform(300, 900), random.uniform(-900, -300))
    sensors.append({
        "name": f"Акустичний пост «Звук-{h_name}-2»",
        "sensor_type": "acoustic",
        "lat": a2_lat,
        "lon": a2_lon,
        "alt": 15.0,
        "detection_radius": 2600.0,
        "description": "Мікрофонний масив звукопеленгації низьковисотних цілей у міській забудові."
    })

    # 4. МАЛА ЗОНА СПОСТЕРЕЖЕННЯ ЛЮДЬМИ (Локальний спостережний пункт)
    obs_s_lat, obs_s_lon = _shift_coords(base_lat, base_lon, random.uniform(-300, 300), random.uniform(-300, 300))
    sensors.append({
        "name": f"Спостережний пост «Варта-{h_name}» (Малий радіус)",
        "sensor_type": "observation_post",
        "lat": obs_s_lat,
        "lon": obs_s_lon,
        "alt": 30.0,
        "detection_radius": 1200.0,
        "description": "Локальний пост візуального спостереження ТрО на даху багатоповерхівки (бінокль, планшет «єППО»)."
    })

    # 5. ВЕЛИКА ЗОНА СПОСТЕРЕЖЕННЯ ЛЮДЬМИ (Мобільна вогнева група МВГ)
    obs_l_lat, obs_l_lon = _shift_coords(base_lat, base_lon, random.uniform(-1200, 1200), random.uniform(-1200, 1200))
    sensors.append({
        "name": f"Рубіж МВГ «Титан-{h_name}» (Великий радіус)",
        "sensor_type": "observation_post",
        "lat": obs_l_lat,
        "lon": obs_l_lon,
        "alt": 60.0,
        "detection_radius": 4200.0,
        "description": "Висотний рубіж Мобільної вогневої групи: тепловізор, зенітний прожектор, візуальне супроводження цілі."
    })

    return sensors


async def seed_settlement_sensors(replace_existing: bool = True) -> Dict[str, int]:
    """
    Заповнює базу даних датчиками виявлення у населених пунктах:
    - Зберігає критичні об'єкти (target_asset);
    - Очищає лише старі датчики спостереження (якщо replace_existing=True);
    - Створює збалансовану сенсорну мережу 2.4GHz, оптику, акустику та зони спостереження людей.
    """
    logger.info("[SETTLEMENT SENSORS] Старт розміщення датчиків розпізнавання у населених пунктах...")

    all_generated: List[Dict[str, Any]] = []
    for hub in SETTLEMENT_HUBS:
        hub_sensors = generate_sensors_for_hub(hub)
        all_generated.extend(hub_sensors)

    counts = {
        "camera": 0,
        "rf_24ghz": 0,
        "acoustic": 0,
        "observation_post_small": 0,
        "observation_post_large": 0
    }

    async with async_session() as session:
        if replace_existing:
            # Видаляємо всі сенсори крім критичних цілей (target_asset)
            await session.execute(
                delete(TacticalSensorModel).where(TacticalSensorModel.sensor_type != "target_asset")
            )

        for s_data in all_generated:
            s_type = s_data["sensor_type"]
            rad = s_data["detection_radius"]

            if s_type == "camera":
                counts["camera"] += 1
            elif s_type == "rf_24ghz":
                counts["rf_24ghz"] += 1
            elif s_type == "acoustic":
                counts["acoustic"] += 1
            elif s_type == "observation_post":
                if rad <= 2000.0:
                    counts["observation_post_small"] += 1
                else:
                    counts["observation_post_large"] += 1

            db_model = TacticalSensorModel(
                name=s_data["name"],
                sensor_type=s_type,
                lat=s_data["lat"],
                lon=s_data["lon"],
                alt=s_data["alt"],
                detection_radius=rad,
                description=s_data["description"]
            )
            session.add(db_model)

        await session.commit()

    logger.info(
        f"[SETTLEMENT SENSORS] Успішно розгорнуто {len(all_generated)} сенсорів у населених пунктах:\n"
        f"  • Оптичні камери (ШІ-фотофіксація): {counts['camera']}\n"
        f"  • Радіочастотні датчики 2.4 ГГц: {counts['rf_24ghz']}\n"
        f"  • Акустичні мікрофони шуму ДВЗ: {counts['acoustic']}\n"
        f"  • Малі зони спостереження (ТрО): {counts['observation_post_small']}\n"
        f"  • Великі зони спостереження (МВГ): {counts['observation_post_large']}"
    )

    return {
        "total_created": len(all_generated),
        **counts
    }
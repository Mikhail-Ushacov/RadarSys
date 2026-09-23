# backend/seed_district.py
import asyncio
import json
from sqlalchemy import delete
from app.database import engine, async_session, Base
from app.models import EWNodeModel, TacticalZoneModel, TacticalSensorModel
from app.config import settings
from app.core.risk_h3 import load_grid, generate_district_zones_from_h3

async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        print("[*] Очищення попередньої тактичної обстановки...")
        await session.execute(delete(EWNodeModel))
        await session.execute(delete(TacticalZoneModel))
        await session.execute(delete(TacticalSensorModel))
        await session.commit()

        base_lat = settings.DATUM_LAT
        base_lon = settings.DATUM_LON

        print("[*] Генерація об'єднаних районів із сітки H3 (Червоні, Помаранчеві, Зелені)...")
        load_grid()
        h3_districts = generate_district_zones_from_h3()

        if h3_districts:
            print(f"[+] Згенеровано {len(h3_districts)} об'єднаних зон з H3-гексагонів!")
            for d in h3_districts:
                session.add(TacticalZoneModel(
                    name=d["name"],
                    zone_type=d["zone_type"],
                    coordinates=json.dumps(d["coordinates"])
                ))
        else:
            print("[!] H3 grid не знайдено, використовується стандартний тактичний набір зон...")
            fallback_zones = [
                TacticalZoneModel(
                    name="Червона зона: Ж/М Оболонь (Забудова)",
                    zone_type="danger",
                    coordinates=json.dumps([
                        [base_lat + 0.045, base_lon - 0.045],
                        [base_lat + 0.075, base_lon - 0.045],
                        [base_lat + 0.075, base_lon - 0.010],
                        [base_lat + 0.045, base_lon - 0.010]
                    ])
                ),
                TacticalZoneModel(
                    name="Червона зона: Ж/М Троєщина (Щільна забудова)",
                    zone_type="danger",
                    coordinates=json.dumps([
                        [base_lat + 0.050, base_lon + 0.035],
                        [base_lat + 0.090, base_lon + 0.035],
                        [base_lat + 0.090, base_lon + 0.075],
                        [base_lat + 0.050, base_lon + 0.075]
                    ])
                ),
                TacticalZoneModel(
                    name="Помаранчева зона: Буфер узбережжя р. Десна",
                    zone_type="caution",
                    coordinates=json.dumps([
                        [base_lat + 0.070, base_lon - 0.015],
                        [base_lat + 0.095, base_lon - 0.015],
                        [base_lat + 0.095, base_lon + 0.015],
                        [base_lat + 0.070, base_lon + 0.015]
                    ])
                ),
                TacticalZoneModel(
                    name="Зелена зона: KILLBOX-A (Заплава р. Десна)",
                    zone_type="safe",
                    coordinates=json.dumps([
                        [base_lat + 0.080, base_lon - 0.005],
                        [base_lat + 0.130, base_lon + 0.010],
                        [base_lat + 0.135, base_lon + 0.045],
                        [base_lat + 0.085, base_lon + 0.030]
                    ])
                ),
                TacticalZoneModel(
                    name="Зелена зона: KILLBOX-B (Пустир & Торфовища)",
                    zone_type="safe",
                    coordinates=json.dumps([
                        [base_lat + 0.090, base_lon + 0.100],
                        [base_lat + 0.140, base_lon + 0.100],
                        [base_lat + 0.140, base_lon + 0.160],
                        [base_lat + 0.090, base_lon + 0.160]
                    ])
                )
            ]
            session.add_all(fallback_zones)

        print("[*] Розміщення комплексів спрямованого РЕБ (Directional EW)...")
        ew_nodes = [
            EWNodeModel(name="РЕБ-1 «ДЕСНА-ЗАХІД»", lat=base_lat + 0.078, lon=base_lon - 0.008, alt=35.0, max_range=4500.0, beamwidth=35.0, current_azimuth=38.0, is_armed=True),
            EWNodeModel(name="РЕБ-2 «ДЕСНА-СХІД»", lat=base_lat + 0.085, lon=base_lon + 0.055, alt=28.0, max_range=4200.0, beamwidth=40.0, current_azimuth=345.0, is_armed=True),
            EWNodeModel(name="РЕБ-3 «КИЇВСЬКЕ МОРЕ»", lat=base_lat + 0.160, lon=base_lon - 0.030, alt=40.0, max_range=5000.0, beamwidth=45.0, current_azimuth=15.0, is_armed=True),
            EWNodeModel(name="РЕБ-4 «БРОВАРИ-РУБІЖ»", lat=base_lat + 0.082, lon=base_lon + 0.125, alt=22.0, max_range=3800.0, beamwidth=35.0, current_azimuth=25.0, is_armed=True)
        ]
        session.add_all(ew_nodes)

        print("[*] Розгортання ешелону сенсорів...")
        sensors = [
            TacticalSensorModel(name="ТЕЦ-6 (Критична інфраструктура)", sensor_type="target_asset", lat=base_lat + 0.065, lon=base_lon + 0.080, detection_radius=800.0, description="Пріоритет №1. Генерація та розподіл електроенергії"),
            TacticalSensorModel(name="Київська ГЕС (Гідроспоруда)", sensor_type="target_asset", lat=base_lat + 0.150, lon=base_lon - 0.035, detection_radius=1000.0, description="Стратегічний гідровузол Дніпровського каскаду"),
            TacticalSensorModel(name="ПС 750кВ «Північна»", sensor_type="target_asset", lat=base_lat + 0.110, lon=base_lon + 0.170, detection_radius=700.0, description="Магістральна вузлова підстанція Укренерго"),
            TacticalSensorModel(name="CAM-PTZ-01 «ВИШКА-ДЕСНА»", sensor_type="camera", lat=base_lat + 0.105, lon=base_lon + 0.015, detection_radius=3200.0, description="Тепловізійний сенсор на телеком-вежі 75м"),
            TacticalSensorModel(name="CAM-PTZ-02 «МАЯК-ВОДОСХОВИЩЕ»", sensor_type="camera", lat=base_lat + 0.165, lon=base_lon - 0.045, detection_radius=3500.0, description="Оптичний канал спостереження акваторії"),
            TacticalSensorModel(name="AUDIO-ARRAY-11 «ПОГРЕБИ»", sensor_type="acoustic", lat=base_lat + 0.095, lon=base_lon + 0.060, detection_radius=3800.0, description="Акустичний масив мікрофонів MD-550"),
            TacticalSensorModel(name="AUDIO-ARRAY-12 «ЛІТКИ»", sensor_type="acoustic", lat=base_lat + 0.145, lon=base_lon + 0.075, detection_radius=4000.0, description="Передовий акустичний пост"),
            TacticalSensorModel(name="МВГ «ХИЖАК-1»", sensor_type="observation_post", lat=base_lat + 0.115, lon=base_lon + 0.005, detection_radius=2000.0, description="Екіпаж мобільної вогневої групи з ПЗРК")
        ]
        session.add_all(sensors)

        await session.commit()
        print("[+] Тактичний район успішно розгорнуто!")

if __name__ == "__main__":
    asyncio.run(seed())
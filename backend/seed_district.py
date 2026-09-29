# backend/seed_sensors.py
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_db
from app.seed.settlement_sensors import seed_settlement_sensors

async def main():
    print("[1/2] Ініціалізація бази даних...")
    await init_db()
    print("[2/2] Генерація камер, 2.4 ГГц, акустики та спостережних постів...")
    result = await seed_settlement_sensors(replace_existing=True)
    print("=" * 60)
    print(f"УСПІШНО РОЗГОРНУТО {result['total_created']} СЕНСОРІВ:")
    print(f"  • Оптичні камери (ШІ-фотофіксація): {result['camera']}")
    print(f"  • Датчики 2.4 ГГц (радіочастотний спектр): {result['rf_24ghz']}")
    print(f"  • Акустичні мікрофони шуму ДВЗ: {result['acoustic']}")
    print(f"  • Малі пости спостереження (ТрО): {result['observation_post_small']}")
    print(f"  • Великі рубежі спостереження (МВГ): {result['observation_post_large']}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
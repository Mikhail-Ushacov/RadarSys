# backend/app/main.py
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.core.risk_h3 import load_grid as risk_load_grid
from app.seed.ci_loader import seed_from_data_files, data_files_watcher_loop
from app.seed.ew_optimizer import auto_optimize_and_apply_ew
from app.services.c2_engine import c2_engine
from app.services.connection_manager import ws_manager
from app.api.v1.router import api_v1_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Ініціалізація бази даних та сітки H3
    await init_db()
    try:
        ok = risk_load_grid()
        logger.info("risk_h3 grid loaded=%s", ok)
    except Exception as e:
        logger.warning("risk_h3 load failed: %s", e)

    # 2. Автоматичний пошук і завантаження ОКІ та тактичних зон із дата-файлів
    try:
        logger.info("[INIT] Завантаження критичної інфраструктури та зон із дата-файлів...")
        await seed_from_data_files(force_reload=True)
    except Exception as e:
        logger.error("[INIT] Помилка завантаження даних із data/: %s", e)

    # 3. Автоматичний запуск оптимізації РЕБ з оцінкою ОКІ/Killbox та радіусом до 10000м
    try:
        logger.info("[INIT] Оцінка ОКІ та зон: запуск оптимізації розташування РЕБ (радіус до 10000м)...")
        await auto_optimize_and_apply_ew(node_count=7, replace_existing=True)
    except Exception as e:
        logger.error("[INIT] Помилка оптимізації РЕБ при старті: %s", e)

    # 4. Фонові цикли:
    #   - C2 Engine (супровід дронів та бойова робота)
    #   - Data Files Watcher (перевірка оновлення data/ci.json та data/tactical_zones.json)
    c2_task = asyncio.create_task(c2_engine.calculation_loop())
    watcher_task = asyncio.create_task(data_files_watcher_loop(interval_sec=4.0))

    yield

    c2_task.cancel()
    watcher_task.cancel()

app = FastAPI(title="Surgical EW Control System", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Підключення всіх API маршрутів v1
app.include_router(api_v1_router)

# WebSocket для оперативного потоку даних C2
@app.websocket("/ws/tactical")
async def websocket_tactical(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
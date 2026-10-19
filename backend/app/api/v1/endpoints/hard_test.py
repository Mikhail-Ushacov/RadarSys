# backend/app/api/v1/endpoints/hard_test.py
import asyncio
from fastapi import APIRouter, Response
from app.services.hard_test_engine import hard_test_engine

router = APIRouter(prefix="/hard_test", tags=["hard_test"])


@router.post("/start")
async def start_hard_test():
    """Запускає розрахунок пришвидшеного стрес-тесту на базі історичних БПЛА."""
    if hard_test_engine.is_running:
        return {"status": "already_running", "progress": hard_test_engine.progress}

    asyncio.create_task(hard_test_engine.run_simulation())
    return {"status": "started", "message": "Hard Test успішно ініціалізовано"}


@router.get("/status")
async def get_hard_test_status():
    """Повертає поточний статус і прогрес симуляції."""
    return {
        "is_running": hard_test_engine.is_running,
        "progress": hard_test_engine.progress,
        "status_message": hard_test_engine.status_message,
        "summary": hard_test_engine.summary,
    }


@router.get("/results")
async def get_hard_test_results():
    """Повертає аналітику та детальну таблицю збитих бортів."""
    return {
        "summary": hard_test_engine.summary,
        "detailed_results": hard_test_engine.detailed_results
    }


@router.get("/export_csv")
async def export_hard_test_csv():
    """Завантажує результати у форматі CSV."""
    csv_content = hard_test_engine.generate_csv()
    filename = f"Hard_Test_EW_Report_{int(asyncio.get_event_loop().time())}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
# backend/app/api/v1/endpoints/seed.py
from fastapi import APIRouter
from app.seed.ci_loader import seed_from_data_files
from app.seed.ew_optimizer import auto_optimize_and_apply_ew

router = APIRouter(tags=["seed"])

@router.post("/seed")
async def run_seed_endpoint():
    result = await seed_from_data_files(force_reload=True)
    await auto_optimize_and_apply_ew(node_count=7, replace_existing=True)
    return {"status": "seed_completed", "details": result}
# backend/app/api/v1/endpoints/seed.py
from fastapi import APIRouter
from seed_district import seed as run_seed

router = APIRouter(tags=["seed"])

@router.post("/seed")
async def run_seed_endpoint():
    await run_seed()
    return {"status": "seed_completed"}
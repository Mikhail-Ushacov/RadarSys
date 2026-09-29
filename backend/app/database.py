# backend/app/database.py
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Безпечне додавання нових колонок для наявної бази SQLite
        for col_def in [
            "drone_type VARCHAR DEFAULT 'Shahed-136 (Герань-2)'",
            "debris_radius_m FLOAT DEFAULT 120.0",
            "emergency_112_called BOOLEAN DEFAULT 0",
            "emergency_details VARCHAR DEFAULT ''"
        ]:
            try:
                await conn.execute(text(f"ALTER TABLE downed_drones ADD COLUMN {col_def}"))
            except Exception:
                pass
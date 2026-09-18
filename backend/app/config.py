from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Центр робочої зони (Datum) для локальних декартових координат ENU (Київ за замовчуванням)
    DATUM_LAT: float = 50.4501
    DATUM_LON: float = 30.5234
    DATUM_ALT: float = 120.0

    DATABASE_URL: str = "sqlite+aiosqlite:///./ew_tactical.db"
    # Для продакшну з PostgreSQL:
    # DATABASE_URL: str = "postgresql+asyncpg://postgres:secret@db:5432/ew_tactical"

    BURST_DEFAULT_SECONDS: int = 20
    WIND_VECTOR_X: float = 3.0  # Знесення вітром (м/с, East)
    WIND_VECTOR_Y: float = -1.5 # Знесення вітром (м/с, North)

    class Config:
        env_file = ".env"

settings = Settings()
"""Validated environment configuration; credentials never belong in source control."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    DATABASE_URL: str = Field(min_length=1)
    DATABASE_MIGRATION_URL: str | None = None
    REDIS_URL: str = "redis://localhost:6379/0"
    APP_ENV: Literal["development", "test", "production"] = "development"
    DATASET_PATH: Path = PROJECT_ROOT / "stocks_ohlc_data.parquet"
    CACHE_DEFAULT_TTL: int = Field(default=300, ge=1)
    REDIS_KEY_PREFIX: str = Field(default="stockapi", pattern=r"^[A-Za-z0-9_-]{1,32}$")
    DEPENDENCY_TIMEOUT_SECONDS: int = Field(default=5, ge=1, le=30)
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=20)
    SCREENING_MAX_CONCURRENCY: int = Field(default=1, ge=1, le=4)
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


settings = Settings()

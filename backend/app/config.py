"""Application configuration.

All settings are loaded from environment variables via Pydantic Settings.
Never hardcode secrets — use the `.env` file (which is git-ignored).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for ThermalWatch AI."""

    # --- Application ---
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg2://thermalwatch:thermalwatch@localhost:5432/thermalwatch"

    # --- NASA FIRMS ---
    FIRMS_MAP_KEY: str = ""
    FIRMS_SATELLITE: str = "VIIRS_NOAA20_NRT"
    FIRMS_AREA: str = "world"
    FIRMS_DAYS: int = 1

    # --- Processing ---
    CLUSTER_DISTANCE_METERS: float = 1000.0
    CLUSTER_TIME_HOURS: float = 72.0
    PERSISTENCE_MIN_DETECTIONS: int = 3

    # Pydantic v2 settings model
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
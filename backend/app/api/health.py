"""Health check endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text
from app.config import settings
from app.db.base import engine
from app.ml.classifier import model_status
from app.ml.weak_classifier import weak_model_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> dict:
    """Return a simple health status.

    This is a lightweight endpoint that does not touch the database.
    A full DB check would be added in production.
    """
    return {
        "status": "ok",
        "service": "ThermalWatch AI",
        "version": "0.1.0",
        "data_mode": "DEMO DATA" if settings.DEMO_MODE else
        "FIRMS SNAPSHOT" if settings.FIRMS_SNAPSHOT_PATH else "LIVE MODE",
        "source_status": "SYNTHETIC_SCENARIOS" if settings.DEMO_MODE else
        "NASA_FIRMS_CAPTURED" if settings.FIRMS_SNAPSHOT_PATH else
        "FIRMS_KEY_CONFIGURED" if settings.FIRMS_MAP_KEY
        and not settings.FIRMS_MAP_KEY.startswith("YOUR_") else "FIRMS_KEY_MISSING",
        "classifier_status": model_status(demo=settings.DEMO_MODE)["status"],
    }


@router.get("/model")
def classifier_health() -> dict:
    """Describe model provenance and schema without exposing the artifact."""
    anomaly = model_status(demo=settings.DEMO_MODE)
    return {**anomaly, "anomaly_detection": anomaly,
            "weak_classifier": weak_model_status() if not settings.DEMO_MODE else
            {"model_loaded": False, "inference_available": False,
             "note": "Real-FIRMS classifier disabled in synthetic demo mode."},
            "data_mode": "DEMO DATA" if settings.DEMO_MODE else
            "FIRMS SNAPSHOT" if settings.FIRMS_SNAPSHOT_PATH else "LIVE MODE"}


@router.get("/database")
def database_health() -> dict:
    from app.db.health import database_status
    return database_status()

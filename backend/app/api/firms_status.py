"""Source, freshness, validation, and storage status for the FIRMS feed."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import ThermalEvent, ThermalObservation

router = APIRouter(prefix="/firms", tags=["ingestion"])


def _freshness(value: str | datetime | None) -> tuple[str, float | None]:
    if not value:
        return "UNKNOWN", None
    try:
        observed_at = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (datetime.now(timezone.utc) - observed_at).total_seconds() / 3600)
        return ("FRESH" if age_hours <= 24 else "STALE"), round(age_hours, 2)
    except ValueError:
        return "UNKNOWN", None


def _feed_status() -> dict:
    """Report the actual data source; a local capture is never called live."""
    if settings.DEMO_MODE:
        return {"status": "SYNTHETIC_DEMO", "data_mode": "DEMO DATA",
                "storage_mode": "SYNTHETIC", "is_live": False, "database_persisted": False,
                "source": "DEMO_SYNTHETIC", "capture_timestamp": None,
                "latest_observation": None, "freshness": "NOT_APPLICABLE",
                "observation_count": None, "event_count": None,
                "validation_status": "NOT_APPLICABLE", "refresh_available": False}

    if settings.FIRMS_SNAPSHOT_PATH:
        try:
            from app.snapshot import snapshot_state

            state = snapshot_state()
        except (FileNotFoundError, ValueError, OSError):
            return {"status": "CAPTURE_UNAVAILABLE", "data_mode": "FIRMS SNAPSHOT",
                    "storage_mode": "LOCAL_CAPTURE", "is_live": False,
                    "database_persisted": False, "source": None,
                    "capture_timestamp": None, "latest_observation": None,
                    "freshness": "UNKNOWN", "observation_count": None,
                    "event_count": None, "validation_status": "UNAVAILABLE",
                    "refresh_available": bool(settings.FIRMS_MAP_KEY)}
        report = state["validation"]
        latest = report.get("latest_observation")
        freshness, age_hours = _freshness(latest)
        return {"status": "SAVED_CAPTURE", "data_mode": "FIRMS SNAPSHOT",
                "storage_mode": "LOCAL_CAPTURE", "is_live": False,
                "database_persisted": False, "source": state["source"],
                "capture_timestamp": state["capture_time"],
                "latest_observation": latest, "freshness": freshness,
                "latest_observation_age_hours": age_hours,
                "observation_count": report["records_accepted"],
                "event_count": len(state["events"]),
                "records_received": report["records_received"],
                "records_rejected": report["records_rejected"],
                "duplicates_removed": report["duplicates_removed"],
                "validation_status": "VALIDATED" if report["records_accepted"] else "NO_VALID_ROWS",
                "rejection_reasons": report["rejection_reasons"],
                "refresh_available": bool(settings.FIRMS_MAP_KEY and not settings.FIRMS_MAP_KEY.startswith("YOUR_"))}

    try:
        with SessionLocal() as db:
            observations = db.query(func.count(ThermalObservation.id)).scalar() or 0
            events = db.query(func.count(ThermalEvent.id)).scalar() or 0
            latest = db.query(func.max(ThermalObservation.timestamp)).scalar()
    except SQLAlchemyError:
        return {"status": "DATABASE_UNAVAILABLE", "data_mode": "LIVE MODE",
                "storage_mode": "DATABASE_UNAVAILABLE", "is_live": False,
                "database_persisted": False, "source": None,
                "capture_timestamp": None, "latest_observation": None,
                "freshness": "UNKNOWN", "observation_count": None,
                "event_count": None, "validation_status": "UNAVAILABLE",
                "refresh_available": bool(settings.FIRMS_MAP_KEY)}
    freshness, age_hours = _freshness(latest)
    return {"status": "DATABASE_PERSISTED", "data_mode": "LIVE MODE",
            "storage_mode": "POSTGRESQL_POSTGIS", "is_live": False,
            "database_persisted": True, "source": None,
            "capture_timestamp": None,
            "latest_observation": latest.isoformat() if latest else None,
            "latest_observation_age_hours": age_hours,
            "freshness": freshness, "observation_count": observations,
            "event_count": events, "validation_status": "DATABASE_RECORDS",
            "refresh_available": bool(settings.FIRMS_MAP_KEY and not settings.FIRMS_MAP_KEY.startswith("YOUR_"))}


@router.get("/status")
def firms_status() -> dict:
    from app.db.health import database_status
    database = database_status()
    return {**_feed_status(), **{key: database[key] for key in (
        "database", "postgis", "database_persisted", "persisted_observations", "persisted_events")},
        "database_checked_at": database["checked_at"]}

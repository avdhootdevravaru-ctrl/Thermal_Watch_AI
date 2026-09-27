"""Authoritative connection and persistence status, independent of serving mode."""
from datetime import datetime, timezone
from sqlalchemy import text
from app.config import settings
from app.db.base import engine


def database_status() -> dict:
    mode = "DEMO DATA" if settings.DEMO_MODE else "FIRMS SNAPSHOT" if settings.FIRMS_SNAPSHOT_PATH else "LIVE MODE"
    result = {"status": "snapshot" if settings.FIRMS_SNAPSHOT_PATH else "error",
              "database": "NOT_CONNECTED", "postgis": "UNAVAILABLE",
              "database_persisted": False, "persisted_observations": 0,
              "persisted_events": 0, "schema_available": False, "data_mode": mode,
              "serving_from": "LOCAL_CAPTURE" if settings.FIRMS_SNAPSHOT_PATH else "DATABASE",
              "checked_at": datetime.now(timezone.utc).isoformat()}
    if settings.DEMO_MODE:
        return {**result, "status": "demo", "database": "not used", "serving_from": "SYNTHETIC",
                "note": "Synthetic demonstration does not use database persistence."}
    try:
        with engine.connect() as connection:
            result["pg_version"] = connection.execute(text("SELECT version()")).scalar_one()
            result["database"] = "CONNECTED"
            result["status"] = "snapshot_with_db" if settings.FIRMS_SNAPSHOT_PATH else "ok"
            try:
                result["postgis_version"] = connection.execute(text("SELECT PostGIS_Version()")).scalar_one()
                result["postgis"] = "AVAILABLE"
            except Exception:
                connection.rollback()
            try:
                result["persisted_observations"] = connection.execute(text("SELECT count(*) FROM thermal_observations")).scalar_one()
                result["persisted_events"] = connection.execute(text("SELECT count(*) FROM thermal_events")).scalar_one()
                result["schema_available"] = True
                result["database_persisted"] = result["persisted_observations"] > 0 and result["persisted_events"] > 0
            except Exception:
                connection.rollback()
        result["note"] = ("Database connection verified. "
                          + ("Dashboard reads the local capture; database counts describe stored records." if settings.FIRMS_SNAPSHOT_PATH else "Dashboard reads database records."))
    except Exception:
        result["note"] = "PostgreSQL connection unavailable. The saved capture remains usable when configured."
    return result

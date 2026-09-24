"""Data processing functions for ThermalWatch AI.

Bridges raw FIRMS data, SQLAlchemy models, and clustering/persistence logic.
All functions are pure (no side effects) where possible.
"""

from __future__ import annotations

import json

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ThermalEvent, ThermalObservation, ObservationSource

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session management helper (used by API handlers)
# ---------------------------------------------------------------------------

def get_db_session() -> Session:
    """Create a new SQLAlchemy session.

    In production, this would be an async session or connection pool.
    Here we return a synchronous session for simplicity.
    """
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return Session(bind=engine)


# ---------------------------------------------------------------------------
# Observation ingestion
# ---------------------------------------------------------------------------

def store_observations(
    observations: List[Dict[str, Any]], db: Session
) -> Dict[str, int]:
    """Store normalized FIRMS observations into the database.

    Performs an upsert based on a unique key (timestamp, latitude, longitude,
    and source) to avoid duplicates on repeated runs.

    Returns a summary:
    {
        "inserted": X,
        "updated": Y,
        "failed": Z,
    }
    """
    if not observations:
        logger.warning("No observations to store")
        return {"inserted": 0, "updated": 0, "failed": 0}

    inserted = 0
    updated = 0
    failed = 0

    for raw in observations:
        try:
            # Normalize observation to our ORM model
            observation = _raw_to_orm(raw)

            # Check if a similar observation already exists
            existing = db.query(ThermalObservation).filter(
                ThermalObservation.timestamp == observation.timestamp,
                ThermalObservation.latitude == observation.latitude,
                ThermalObservation.longitude == observation.longitude,
                ThermalObservation.source == observation.source,
            ).first()

            if existing:
                # Update fields that may have changed (intensity/confidence)
                existing.intensity = observation.intensity
                existing.confidence = observation.confidence
                existing.source = observation.source
                existing.sensor = observation.sensor
                existing.metadata_json = observation.metadata_json
                db.commit()
                updated += 1
            else:
                db.add(observation)
                inserted += 1

            # Every N observations, flush to avoid long transactions
            if (inserted + updated) % 50 == 0:
                db.flush()

        except Exception as e:
            logger.exception("Failed to store observation: %s", e)
            db.rollback()
            failed += 1

    logger.info(
        "Observation storage completed: inserted=%d updated=%d failed=%d",
        inserted,
        updated,
        failed,
    )

    # Commit uncommitted inserts so they survive a later clustering rollback
    db.commit()

    return {"inserted": inserted, "updated": updated, "failed": failed}


def _raw_to_orm(raw: Dict[str, Any]) -> ThermalObservation:
    """Convert a normalized observation dict into a ThermalObservation model.

    Handles datetime, numeric coercion, and geometry.
    """
    # Ensure timestamp is timezone-aware UTC
    ts = raw["timestamp"]
    if ts and ts.tzinfo is None:
        # Assume UTC if naive
        from datetime import timezone
        ts = ts.replace(tzinfo=timezone.utc)

    # Create geometry from lat/lon (using GeoAlchemy2)
    from geoalchemy2 import WKTElement
    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point

    if raw["latitude"] is not None and raw["longitude"] is not None:
        geom = from_shape(Point(raw["longitude"], raw["latitude"]), srid=4326)
    else:
        # Create empty geometry if missing
        geom = WKTElement("POINT EMPTY", srid=4326)

    return ThermalObservation(
        timestamp=ts,
        latitude=raw["latitude"],
        longitude=raw["longitude"],
        intensity=raw.get("intensity"),
        confidence=raw.get("confidence"),
        source=raw.get("source", "UNKNOWN"),
        sensor=raw.get("sensor"),
        metadata_json=_json_safe(raw.get("metadata", {})),
        geometry=geom,
    )


def _json_safe(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable values (datetime, etc.) to ISO strings.

    PostgreSQL JSONB columns require JSON-serializable data; passing a raw
    datetime/date object causes "Object of type datetime is not JSON serializable".
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    return str(obj)


# ---------------------------------------------------------------------------
# Event clustering and persistence detection
# ---------------------------------------------------------------------------

def process_observations(
    db: Session,
    cluster_distance_meters: float = settings.CLUSTER_DISTANCE_METERS,
    cluster_time_hours: float = settings.CLUSTER_TIME_HOURS,
) -> Dict[str, int]:
    """Run the full event detection pipeline on the latest FIRMS data.

    Steps:
      1. Fetch FIRMS observations (or accept them as input, to be added)
      2. Store new observations (upsert)
      3. Cluster observations into events
      4. Mark events as persistent or temporary
      5. Link observations to events in the DB

    Returns a summary of what was created/updated.
    """
    # TODO: Accept observations as parameter when we add a test pipeline
    # For now, just run on whatever is currently in the DB (to be populated)
    all_observations = db.query(ThermalObservation).all()
    if not all_observations:
        logger.info("No FIRMS observations in DB; skipping clustering")
        return {"events_created": 0, "events_updated": 0}

    # Convert observations to normalized dicts (this is a bit inefficient but OK for now)
    observation_dicts = [
        {
            "latitude": obs.latitude,
            "longitude": obs.longitude,
            "timestamp": obs.timestamp,
            "intensity": obs.intensity,
            "confidence": obs.confidence,
            "source": obs.source,
            "sensor": obs.sensor,
            "metadata": obs.metadata_json,
            "event_id": obs.event_id,
        }
        for obs in all_observations
    ]

    # Run clustering
    events = cluster_observations(observation_dicts, cluster_distance_meters, cluster_time_hours)

    # Process each event
    events_created = 0
    events_updated = 0

    for event in events:
        # Check if event already exists (based on centroid and time range)
        existing = db.query(ThermalEvent).filter(
            (ThermalEvent.latitude.between(event["centroid_lat"] - 0.001, event["centroid_lat"] + 0.001)) &
            (ThermalEvent.longitude.between(event["centroid_lon"] - 0.001, event["centroid_lon"] + 0.001)) &
            (ThermalEvent.start_time == event["start_time"]) &
            (ThermalEvent.end_time == event["end_time"])
        ).first()

        if existing:
            # Update event attributes
            existing.observation_count = event["observation_count"]
            existing.persistence_score = event.get("persistence_score", 0.0)
            existing.status = event.get("status", "ACTIVE")
            events_updated += 1
        else:
            new_event = ThermalEvent(
                latitude=event["centroid_lat"],
                longitude=event["centroid_lon"],
                start_time=event["start_time"],
                end_time=event["end_time"],
                observation_count=event["observation_count"],
                persistence_score=event.get("persistence_score", 0.0),
                status=event.get("status", "ACTIVE")
            )
            db.add(new_event)
            db.flush()
            events_created += 1

    db.commit()
    logger.info(
        "Event processing completed: created=%d updated=%d",
        events_created,
        events_updated,
    )

    return {"events_created": events_created, "events_updated": events_updated}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def get_recent_observations(hours: int = 24, db: Optional[Session] = None) -> List[ThermalObservation]:
    """Get observations from the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    session = db or get_db_session()
    return session.query(ThermalObservation).filter(ThermalObservation.timestamp >= cutoff).all()


def get_events_by_status(status: str, db: Optional[Session] = None) -> List[ThermalEvent]:
    """Get events filtered by status."""
    session = db or get_db_session()
    return session.query(ThermalEvent).filter(ThermalEvent.status == status).all()


def get_all_observations(db: Optional[Session] = None) -> List[ThermalObservation]:
    """Get all observations from the database."""
    session = db or get_db_session()
    return session.query(ThermalObservation).all()
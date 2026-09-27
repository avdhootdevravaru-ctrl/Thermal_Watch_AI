"""FIRMS ingestion endpoint.

POST /ingestion/firms/run — triggers a new FIRMS data fetch and stores the results.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import ThermalEvent, ThermalObservation
from app.ingestion.firms_client import FirmsClient
from app.ingestion.validation import validate_firms_csv
from app.ingestion.normalizer import normalize_observation
from app.processing.clustering import cluster_observations, assign_observations_to_events
from app.processing.persistence import detect_persistent_sources, compute_persistence_score
from app.processing.risk import filter_india_observations, generate_risk_assessment
from app.processing.functions import store_observations
from app.schemas.ingestion import IngestionResult, IngestionRunRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/firms/run", response_model=IngestionResult)
async def run_firms_ingestion(
    request: Optional[IngestionRunRequest] = None,
    db: Session = Depends(get_db),
) -> IngestionResult:
    """Trigger a FIRMS data ingestion run.

    Fetches the latest thermal observations from NASA FIRMS, normalizes them,
    stores them in the database, and clusters them into thermal events.

    Returns a summary of what was created/updated.
    """
    started_at = datetime.now(timezone.utc)

    # Determine effective parameters (request overrides config)
    satellite = (request.satellite if request and request.satellite else settings.FIRMS_SATELLITE)
    area = (request.area if request and request.area else settings.FIRMS_AREA)
    days = (request.days if request and request.days else settings.FIRMS_DAYS)

    logger.info(
        "Starting FIRMS ingestion: satellite=%s area=%s days=%d",
        satellite, area, days,
    )

    errors: list[str] = []
    events_created = 0
    events_updated = 0
    persistent: list = []
    invalid_coordinates = 0
    missing_critical_fields = 0
    duplicates = 0

    # --- Step 1: Fetch FIRMS data ---
    if not settings.FIRMS_MAP_KEY or settings.FIRMS_MAP_KEY.startswith("YOUR_"):
        logger.error("FIRMS_MAP_KEY is not configured")
        errors.append("FIRMS_MAP_KEY is not configured. Please set your NASA FIRMS API key in the .env file.")
        return IngestionResult(
            status="failed",
            observations_fetched=0,
            observations_stored=0,
            observations_failed=0,
            events_created=0,
            events_updated=0,
            persistent_sources=0,
            observations_invalid_coordinates=invalid_coordinates,
            observations_missing_critical_fields=missing_critical_fields,
            observations_duplicate=duplicates,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            errors=errors,
        )

    try:
        client = FirmsClient(
            map_key=settings.FIRMS_MAP_KEY,
            satellite=satellite,
            area=area,
            days=days,
        )
        raw_csv = client.fetch_csv()
        normalized, report = validate_firms_csv(raw_csv, source=satellite)
    except Exception as e:
        # httpx exceptions may contain the request URL, including MAP_KEY.
        logger.error("FIRMS fetch failed (%s)", type(e).__name__)
        errors.append("FIRMS fetch failed. Check API key, product, network, and FIRMS service status.")
        return IngestionResult(
            status="failed",
            observations_fetched=0,
            observations_stored=0,
            observations_failed=0,
            events_created=0,
            events_updated=0,
            persistent_sources=0,
            observations_invalid_coordinates=invalid_coordinates,
            observations_missing_critical_fields=missing_critical_fields,
            observations_duplicate=duplicates,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            errors=errors,
        )

    if report.records_received == 0:
        logger.warning("FIRMS returned no observations")
        errors.append("FIRMS returned no observations")
        return IngestionResult(
            status="partial",
            observations_fetched=0,
            observations_stored=0,
            observations_failed=0,
            events_created=0,
            events_updated=0,
            persistent_sources=0,
            observations_invalid_coordinates=invalid_coordinates,
            observations_missing_critical_fields=missing_critical_fields,
            observations_duplicate=duplicates,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            errors=errors,
        )

    # --- Step 2: Use the same audited validator as local FIRMS replay ---
    invalid_coordinates = report.invalid_coordinates
    missing_critical_fields = report.rejection_reasons.get("MISSING_COORDINATES", 0) + report.invalid_timestamps
    duplicates = report.duplicates_removed

    # Filter to India only (user requirement: India geographic containment)
    india_observations = filter_india_observations(normalized)
    filtered_count = len(normalized) - len(india_observations)
    if filtered_count > 0:
        logger.info("Filtered out %d observations outside India boundaries", filtered_count)

    # Use India-filtered observations for storage and clustering
    filtered_normalized = india_observations

    # --- Step 3: Store observations in DB ---
    try:
        store_result = store_observations(filtered_normalized, db)
    except Exception as e:
        logger.exception("Store observations failed: %s", e)
        db.rollback()
        errors.append("Database storage failed; check PostgreSQL/PostGIS connection and schema.")
        store_result = {"inserted": 0, "updated": 0, "failed": 0}

    # --- Step 4: Cluster observations into events ---
    try:
        # Only cluster recent observations to keep the DBSCAN distance matrix manageable.
        # Limit to the last 2 days — the vast majority of fire observations are from
        # recent satellite passes. Historical data is already stored and accessible.
        # (full N×N matrix = N² × 8 bytes; 1K obs ≈ 8MB, 5K obs ≈ 200MB)
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        all_obs = db.query(ThermalObservation).filter(
            ThermalObservation.timestamp >= cutoff
        ).all()
        observation_dicts = [
            {
                "id": obs.id,
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
            for obs in all_obs
        ]

        events = cluster_observations(
            observation_dicts,
            distance_meters=settings.CLUSTER_DISTANCE_METERS,
            time_hours=settings.CLUSTER_TIME_HOURS,
        )

        # Mark persistent sources
        persistent = detect_persistent_sources(
            events,
            min_detections=settings.PERSISTENCE_MIN_DETECTIONS,
        )

        # Create / update ThermalEvent rows FIRST (to get DB-generated IDs)
        events_created = 0
        events_updated = 0
        # Map cluster event index (0-based) → DB event id
        cluster_to_db_id: dict[int, int] = {}

        for event_idx, event in enumerate(events):
            existing = db.query(ThermalEvent).filter(
                (ThermalEvent.latitude.between(event["centroid_lat"] - 0.001, event["centroid_lat"] + 0.001)) &
                (ThermalEvent.longitude.between(event["centroid_lon"] - 0.001, event["centroid_lon"] + 0.001)) &
                (ThermalEvent.start_time == event["start_time"]) &
                (ThermalEvent.end_time == event["end_time"])
            ).first()

            if existing:
                existing.observation_count = event["observation_count"]
                existing.persistence_score = event.get("persistence_score", 0.0)
                existing.status = event.get("status", "ACTIVE")
                cluster_to_db_id[event_idx] = existing.id
                events_updated += 1
            else:
                new_event = ThermalEvent(
                    latitude=event["centroid_lat"],
                    longitude=event["centroid_lon"],
                    start_time=event["start_time"],
                    end_time=event["end_time"],
                    observation_count=event["observation_count"],
                    persistence_score=event.get("persistence_score", 0.0),
                    status=event.get("status", "ACTIVE"),
                )
                db.add(new_event)
                db.flush()  # get the DB-generated id without full commit
                cluster_to_db_id[event_idx] = new_event.id
                events_created += 1

        # Now link observations to events using the real DB event IDs.
        # `cluster_observations` filters out observations with missing lat/lon/timestamp
        # and indexes the remaining ones in `parsed`. Build that same filter here so
        # observation_indices line up with the indices used by the clustering.
        valid_obs_with_ids = [
            (d["id"], d)
            for d in observation_dicts
            if d.get("latitude") is not None
            and d.get("longitude") is not None
            and d.get("timestamp") is not None
        ]
        obs_by_id = {obs.id: obs for obs in all_obs}
        # Track actual observation counts per event during linking
        event_obs_counts: dict[int, int] = {}
        for event_idx, event in enumerate(events):
            db_event_id = cluster_to_db_id.get(event_idx)
            if db_event_id is None:
                continue
            for obs_idx in event.get("observation_indices", []):
                if 0 <= obs_idx < len(valid_obs_with_ids):
                    obs_id = valid_obs_with_ids[obs_idx][0]
                    if obs_id in obs_by_id:
                        obs_by_id[obs_id].event_id = db_event_id
                        event_obs_counts[db_event_id] = event_obs_counts.get(db_event_id, 0) + 1

        # Recalculate observation_count for every created/updated event from the
        # observations actually linked to it, so the column always reflects reality.
        # Count is tracked in-memory during linking (above) rather than querying
        # the DB, because the FK updates haven't been committed yet.
        for db_event_id, actual_count in event_obs_counts.items():
            db.query(ThermalEvent).filter(ThermalEvent.id == db_event_id).update(
                {"observation_count": actual_count}
            )

        db.commit()

        # --- Step 4b: Generate risk assessments for all events ---
        for event_id in cluster_to_db_id.values():
            try:
                event = db.query(ThermalEvent).filter(ThermalEvent.id == event_id).first()
                if event:
                    obs_for_event = db.query(ThermalObservation).filter(
                        ThermalObservation.event_id == event_id
                    ).all()
                    persistence = compute_persistence_score(obs_for_event)
                    # Convert observations to dicts for risk module
                    obs_dicts = [
                        {
                            "id": o.id,
                            "latitude": o.latitude,
                            "longitude": o.longitude,
                            "timestamp": o.timestamp,
                            "intensity": o.intensity,
                            "confidence": o.confidence,
                        }
                        for o in obs_for_event
                    ]
                    generate_risk_assessment(event_id, persistence, obs_dicts, db)
            except Exception as risk_err:
                logger.warning("Failed to generate risk assessment for event %d: %s", event_id, risk_err)
    except Exception as e:
        logger.exception("Clustering failed: %s", e)
        db.rollback()
        errors.append("Database clustering failed; check PostgreSQL/PostGIS connection and schema.")
        events_created = 0
        events_updated = 0
        persistent = []

    # --- Step 5: Return summary ---
    completed_at = datetime.now(timezone.utc)

    return IngestionResult(
        status="success" if not errors else "partial",
        observations_fetched=report.records_received,
        observations_stored=store_result.get("inserted", 0),
        observations_failed=store_result.get("failed", 0) + report.records_rejected,
        events_created=events_created,
        events_updated=events_updated,
        persistent_sources=len(persistent),
        observations_invalid_coordinates=invalid_coordinates,
        observations_missing_critical_fields=missing_critical_fields,
        observations_duplicate=duplicates,
        started_at=started_at,
        completed_at=completed_at,
        errors=errors,
        storage_backend="POSTGIS", records_accepted=report.records_accepted,
        records_rejected=report.records_rejected,
    )

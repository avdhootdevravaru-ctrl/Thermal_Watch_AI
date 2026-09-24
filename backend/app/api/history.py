"""Historical thermal intelligence API endpoints.

Exposes Thermal DNA, historical statistics, baseline, and comparison
functionality through the FastAPI architecture.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import ThermalEvent, ThermalObservation, ThermalProfile
from app.processing.thermal_profile import (
    BASELINE_STATUS,
    compare_current_vs_baseline,
    compute_baseline,
    compute_historical_statistics,
    compute_thermal_profile,
    compute_location_specific_statistics,
)
from app.processing.quality import get_data_quality_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["historical intelligence"])


@router.get("/data-quality", tags=["historical intelligence"])
async def get_historical_data_quality(
    start_date: Optional[datetime] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="End date (exclusive)"),
    db: Session = Depends(get_db),
) -> dict:
    """Get comprehensive historical data quality report."""
    return get_data_quality_report(db, start_date=start_date, end_date=end_date)


@router.get("/statistics", tags=["historical intelligence"])
async def get_historical_statistics(
    start_date: Optional[datetime] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[datetime] = Query(None, description="End date (exclusive)"),
    db: Session = Depends(get_db),
) -> dict:
    """Get historical thermal statistics."""
    return compute_historical_statistics(db, start_date=start_date, end_date=end_date)


@router.get("/location/{lat}/{lon}/statistics", tags=["historical intelligence"])
async def get_location_statistics(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(50.0, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """Get location-specific historical statistics."""
    return compute_location_specific_statistics(db, lat, lon, radius_km)


@router.get("/location/{lat}/{lon}/baseline", tags=["historical intelligence"])
async def get_location_baseline(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(50.0, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """Get location-specific historical baseline."""
    return compute_baseline(db, lat, lon, radius_km)


@router.post("/location/{lat}/{lon}/compare", tags=["historical intelligence"])
async def compare_location_to_baseline(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(50.0, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """Compare current observations against location-specific baseline."""
    baseline = compute_baseline(db, lat, lon, radius_km)

    if baseline.get("status") != BASELINE_STATUS["SUFFICIENT"]:
        return {
            "status": "INSUFFICIENT_HISTORY",
            "note": "Insufficient historical data for comparison",
            "baseline_status": baseline.get("status"),
            "deviations": None,
            "is_ml": False,
        }

    # Use most recent observations as current
    current = db.query(ThermalObservation).filter(
        ThermalObservation.latitude >= lat - (radius_km / 111.0),
        ThermalObservation.latitude <= lat + (radius_km / 111.0),
        ThermalObservation.longitude >= lon - (radius_km / (111.0 * 0.8)),
        ThermalObservation.longitude <= lon + (radius_km / (111.0 * 0.8)),
        ThermalObservation.timestamp >= datetime.now() - timedelta(days=1),
    ).all()

    comparison = compare_current_vs_baseline(current, baseline)
    comparison["baseline_status"] = baseline.get("status")
    return comparison


@router.get("/event/{event_id}/profile", tags=["historical intelligence"])
async def get_event_profile(
    event_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get computed Thermal DNA profile for an event."""
    event = db.query(ThermalEvent).filter(ThermalEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    observations = db.query(ThermalObservation).filter(
        ThermalObservation.event_id == event_id
    ).all()

    profile = compute_thermal_profile(event_id, observations, db)
    return profile


@router.post("/event/{event_id}/profile", tags=["historical intelligence"])
async def compute_event_profile(
    event_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Compute and persist Thermal DNA profile for an event."""
    event = db.query(ThermalEvent).filter(ThermalEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    observations = db.query(ThermalObservation).filter(
        ThermalObservation.event_id == event_id
    ).all()

    profile = compute_thermal_profile(event_id, observations, db)

    # Upsert into database
    existing = db.query(ThermalProfile).filter(ThermalProfile.event_id == event_id).first()
    if existing:
        db.delete(existing)
        db.flush()

    # Convert computed profile to ORM object
    profile_obj = _profile_to_orm(event_id, profile)
    db.add(profile_obj)
    db.commit()
    db.refresh(profile_obj)

    return profile


def _profile_to_orm(event_id: int, profile: dict) -> ThermalProfile:
    """Convert computed profile dictionary to ThermalProfile ORM object."""
    temporal = profile.get("temporal_features", {})
    intensity = profile.get("intensity_features", {})
    spatial = profile.get("spatial_features", {})
    persistence = profile.get("persistence_features", {})
    data_quality = profile.get("data_quality", {})

    return ThermalProfile(
        event_id=event_id,
        first_detection=_parse_datetime(temporal.get("first_detection")),
        last_detection=_parse_datetime(temporal.get("last_detection")),
        active_days=temporal.get("active_days"),
        duration_hours=temporal.get("event_duration_hours"),
        detection_frequency=temporal.get("detection_frequency"),
        recurrence=temporal.get("recurrence"),
        temporal_pattern=temporal.get("temporal_trend"),
        trend=temporal.get("temporal_trend"),
        average_intensity=intensity.get("mean_brightness_temperature"),
        max_intensity=intensity.get("max_brightness_temperature"),
        min_intensity=intensity.get("min_brightness_temperature"),
        intensity_variance=intensity.get("intensity_variance"),
        intensity_trend=intensity.get("intensity_trend"),
        frp_mean=intensity.get("frp_statistics", {}).get("mean") if intensity.get("frp_statistics") else None,
        frp_max=intensity.get("frp_statistics", {}).get("max") if intensity.get("frp_statistics") else None,
        centroid_lat=spatial.get("centroid_lat"),
        centroid_lon=spatial.get("centroid_lon"),
        spatial_spread=spatial.get("spatial_spread"),
        spatial_variance=spatial.get("spatial_variance"),
        spatial_stability=spatial.get("spatial_stability"),
        distinct_detections=spatial.get("distinct_detections"),
        persistence_score=persistence.get("persistence_score"),
        consecutive_active_days=persistence.get("consecutive_active_days"),
        persistence_type=persistence.get("persistence_type"),
        observation_count=profile.get("observation_count", 0),
        confidence_distribution=data_quality.get("confidence_distribution"),
        source_distribution=data_quality.get("source_distribution"),
        data_completeness=data_quality.get("completeness"),
        baseline=profile.get("baseline"),
        baseline_status=profile.get("baseline_status"),
        baseline_deviation=profile.get("baseline_deviation"),
        frequency=temporal.get("detection_frequency", 0.0) or 0.0,
    )


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
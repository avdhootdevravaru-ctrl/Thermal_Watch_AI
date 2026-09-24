"""Historical data quality monitoring and metrics.

Provides comprehensive data quality reports for the ThermalWatch AI system,
distinguishing genuine data issues from processing artifacts.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import ThermalObservation, ThermalEvent

logger = logging.getLogger(__name__)


def get_data_quality_report(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Generate comprehensive data quality report.

    Args:
        db: Database session
        start_date: Optional start date for filtering (inclusive)
        end_date: Optional end date for filtering (exclusive)

    Returns:
        Dictionary containing data quality metrics
    """
    query = db.query(ThermalObservation)

    if start_date:
        query = query.filter(ThermalObservation.timestamp >= start_date)
    if end_date:
        query = query.filter(ThermalObservation.timestamp < end_date)

    observations = query.all()
    observation_count = len(observations)

    if observation_count == 0:
        return _empty_report()

    # Basic counts
    coords_valid = sum(1 for o in observations if o.latitude is not None and o.longitude is not None)
    coords_invalid = observation_count - coords_valid
    timestamps_valid = sum(1 for o in observations if o.timestamp is not None)
    timestamps_invalid = observation_count - timestamps_valid
    critical_fields_valid = sum(1 for o in observations
                              if o.latitude is not None and o.longitude is not None and o.timestamp is not None)
    missing_critical_fields = observation_count - critical_fields_valid

    # Source distribution
    source_counts = defaultdict(int)
    for o in observations:
        source_counts[o.source or "UNKNOWN"] += 1
    source_distribution = dict(source_counts)

    # Confidence distribution (bucketed)
    confidence_values = [o.confidence for o in observations if o.confidence is not None]
    confidence_distribution = _bucket_confidence(confidence_values)

    # Duplicate observations (same lat/lon/timestamp)
    duplicate_count = _count_duplicates(observations)

    # Invalid coordinates (present but out of range)
    invalid_coords = _count_invalid_coordinates(observations)

    # Missing critical fields
    missing_latitude = sum(1 for o in observations if o.latitude is None)
    missing_longitude = sum(1 for o in observations if o.longitude is None)
    missing_timestamp = sum(1 for o in observations if o.timestamp is None)

    # Events metrics
    events_query = db.query(ThermalEvent)
    if start_date:
        events_query = events_query.filter(ThermalEvent.start_time >= start_date)
    if end_date:
        events_query = events_query.filter(ThermalEvent.start_time < end_date)

    events = events_query.all()
    event_count = len(events)

    # Observations per event
    obs_per_event = _observations_per_event(db, events) if events else []

    # Orphan events
    orphan_events = _count_orphan_events(db, events) if events else 0

    # Observation count mismatches
    observation_count_mismatches = _count_observation_count_mismatches(db, events) if events else 0

    # Recurring locations (spatial clustering of detections)
    recurring_locations = _find_recurring_locations(observations)

    # Temporal coverage
    date_range = _get_date_range(observations)

    return {
        "observation_count": observation_count,
        "date_range": date_range,
        "coordinate_validation": {
            "valid": coords_valid,
            "invalid": coords_invalid,
            "missing_latitude": missing_latitude,
            "missing_longitude": missing_longitude,
        },
        "timestamp_validation": {
            "valid": timestamps_valid,
            "invalid": timestamps_invalid,
            "missing": missing_timestamp,
        },
        "critical_fields": {
            "valid": critical_fields_valid,
            "missing": missing_critical_fields,
        },
        "source_distribution": source_distribution,
        "confidence_distribution": confidence_distribution,
        "duplicate_observations": duplicate_count,
        "invalid_coordinates": invalid_coords,
        "event_metrics": {
            "total_events": event_count,
            "observations_per_event": obs_per_event,
            "orphan_events": orphan_events,
            "observation_count_mismatches": observation_count_mismatches,
        },
        "recurring_locations": recurring_locations,
        "data_freshness": {
            "latest_observation": max(o.timestamp for o in observations if o.timestamp is not None) if any(o.timestamp for o in observations) else None,
            "earliest_observation": min(o.timestamp for o in observations if o.timestamp is not None) if any(o.timestamp for o in observations) else None,
        }
    }


def _empty_report() -> Dict[str, Any]:
    """Return empty report structure."""
    return {
        "observation_count": 0,
        "date_range": {"start": None, "end": None, "days": 0},
        "coordinate_validation": {"valid": 0, "invalid": 0, "missing_latitude": 0, "missing_longitude": 0},
        "timestamp_validation": {"valid": 0, "invalid": 0, "missing": 0},
        "critical_fields": {"valid": 0, "missing": 0},
        "source_distribution": {},
        "confidence_distribution": {},
        "duplicate_observations": 0,
        "invalid_coordinates": 0,
        "event_metrics": {
            "total_events": 0,
            "observations_per_event": [],
            "orphan_events": 0,
            "observation_count_mismatches": 0,
        },
        "recurring_locations": [],
        "data_freshness": {"latest_observation": None, "earliest_observation": None}
    }


def _bucket_confidence(values: List[float]) -> Dict[str, int]:
    """Bucket confidence values into ranges."""
    buckets = {
        "0-20": 0,
        "20-40": 0,
        "40-60": 0,
        "60-80": 0,
        "80-100": 0,
        "null": 0
    }

    for val in values:
        if val is None:
            buckets["null"] += 1
        elif val < 20:
            buckets["0-20"] += 1
        elif val < 40:
            buckets["20-40"] += 1
        elif val < 60:
            buckets["40-60"] += 1
        elif val < 80:
            buckets["60-80"] += 1
        else:
            buckets["80-100"] += 1

    # Remove null bucket if no nulls
    if buckets["null"] == 0:
        del buckets["null"]

    return buckets


def _count_duplicates(observations: List[ThermalObservation]) -> int:
    """Count duplicate observations (same location + timestamp)."""
    seen = set()
    duplicates = 0

    for obs in observations:
        if obs.timestamp is None or obs.latitude is None or obs.longitude is None:
            continue

        # Round to reasonable precision to avoid floating point issues
        lat_round = round(float(obs.latitude), 4)
        lon_round = round(float(obs.longitude), 4)
        ts_key = obs.timestamp.isoformat() if obs.timestamp else None

        key = (lat_round, lon_round, ts_key)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)

    return duplicates


def _count_invalid_coordinates(observations: List[ThermalObservation]) -> int:
    """Count coordinates that are present but out of valid range."""
    invalid = 0

    for obs in observations:
        if obs.latitude is not None and not (-90 <= obs.latitude <= 90):
            invalid += 1
        if obs.longitude is not None and not (-180 <= obs.longitude <= 180):
            invalid += 1

    return invalid


def _observations_per_event(db: Session, events: List[ThermalEvent]) -> List[int]:
    """Get observation count for each event."""
    if not events:
        return []

    event_ids = [e.id for e in events]
    obs_counts = db.query(
        ThermalObservation.event_id,
        func.count(ThermalObservation.id)
    ).filter(
        ThermalObservation.event_id.in_(event_ids)
    ).group_by(
        ThermalObservation.event_id
    ).all()

    # Map event_id to count
    count_map = {event_id: count for event_id, count in obs_counts}
    return [count_map.get(e.id, 0) for e in events]


def _count_orphan_events(db: Session, events: List[ThermalEvent]) -> int:
    """Count events with zero linked observations."""
    if not events:
        return 0

    event_ids = [e.id for e in events]
    orphan_count = db.query(func.count(ThermalEvent.id)).filter(
        ThermalEvent.id.in_(event_ids),
        ~ThermalEvent.id.in_(
            db.query(ThermalObservation.event_id)
            .filter(ThermalObservation.event_id.is_not(None))
            .distinct()
        )
    ).scalar()

    return orphan_count or 0


def _count_observation_count_mismatches(db: Session, events: List[ThermalEvent]) -> int:
    """Count events where observation_count doesn't match actual linked observations."""
    if not events:
        return 0

    mismatch_count = 0
    for event in events:
        actual_count = db.query(func.count(ThermalObservation.id)).filter(
            ThermalObservation.event_id == event.id
        ).scalar() or 0

        if event.observation_count != actual_count:
            mismatch_count += 1

    return mismatch_count


def _find_recurring_locations(observations: List[ThermalObservation]) -> List[Dict[str, Any]]:
    """Find locations with recurring detections."""
    if len(observations) < 2:
        return []

    # Group observations by rounded location
    location_groups = defaultdict(list)

    for obs in observations:
        if obs.latitude is None or obs.longitude is None:
            continue

        # Round to ~1km precision
        lat_key = round(float(obs.latitude), 3)
        lon_key = round(float(obs.longitude), 3)
        location_groups[(lat_key, lon_key)].append(obs)

    # Find locations with multiple detections on different days
    recurring = []
    for (lat, lon), obs_list in location_groups.items():
        if len(obs_list) >= 2:
            # Check if detections are on different days
            dates = set()
            for obs in obs_list:
                if obs.timestamp:
                    dates.add(obs.timestamp.date())

            if len(dates) >= 2:  # Multiple detections on different days
                recurring.append({
                    "latitude": lat,
                    "longitude": lon,
                    "detection_count": len(obs_list),
                    "unique_days": len(dates),
                    "first_seen": min(o.timestamp for o in obs_list if o.timestamp).isoformat() if any(o.timestamp for o in obs_list) else None,
                    "last_seen": max(o.timestamp for o in obs_list if o.timestamp).isoformat() if any(o.timestamp for o in obs_list) else None,
                })

    # Sort by detection count descending
    recurring.sort(key=lambda x: x["detection_count"], reverse=True)
    return recurring[:10]  # Top 10 recurring locations


def _get_date_range(observations: List[ThermalObservation]) -> Dict[str, Any]:
    """Get date range of observations."""
    valid_timestamps = [o.timestamp for o in observations if o.timestamp is not None]
    if not valid_timestamps:
        return {"start": None, "end": None, "days": 0, "span_days": 0}

    start_date = min(valid_timestamps)
    end_date = max(valid_timestamps)
    span_days = (end_date - start_date).days + 1

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "days": span_days,
        "unique_dates": len({ts.date() for ts in valid_timestamps})
    }
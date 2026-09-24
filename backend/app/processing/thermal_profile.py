"""Thermal DNA / Thermal Profile computation.

Computes defensible behavioral fingerprints of thermal events from
genuine database observations. Uses explicit NULL/UNKNOWN/INSUFFICIENT_DATA
semantics rather than fabricated values.

Minimum data requirements for each feature are documented inline.
"""

from __future__ import annotations

import logging
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.db.models import ThermalObservation, ThermalEvent, ThermalProfile

logger = logging.getLogger(__name__)

# Minimum observations required for each Thermal DNA feature
MIN_OBSERVATIONS = {
    "temporal_features": 2,
    "intensity_features": 1,
    "spatial_features": 2,
    "persistence_features": 2,
    "data_quality": 1,
}

# States for baseline status
BASELINE_STATUS = {
    "SUFFICIENT": "SUFFICIENT_HISTORY",
    "INSUFFICIENT": "INSUFFICIENT_HISTORY",
    "NO_DATA": "NO_HISTORY",
}


def compute_thermal_profile(
    event_id: int,
    observations: List[ThermalObservation],
    db: Session,
) -> Dict[str, Any]:
    """Compute Thermal DNA profile for a thermal event.

    Calculates defensible characteristics of thermal behavior from
    genuine database observations. Features marked as None indicate
    insufficient data for that calculation.

    Args:
        event_id: ThermalEvent ID
        observations: List of ThermalObservation objects for this event
        db: Database session

    Returns:
        Dictionary containing Thermal DNA features with explicit
        NULL/UNKNOWN/INSUFFICIENT_DATA semantics where data is insufficient
    """
    if not observations:
        return {
            "event_id": event_id,
            "observation_count": 0,
            "status": BASELINE_STATUS["NO_DATA"],
            "temporal_features": _insufficient("temporal_features"),
            "intensity_features": _insufficient("intensity_features"),
            "spatial_features": _insufficient("spatial_features"),
            "persistence_features": _insufficient("persistence_features"),
            "data_quality": _insufficient_data_quality(0),
            "baseline": None,
            "baseline_status": BASELINE_STATUS["NO_DATA"],
        }

    n_obs = len(observations)

    # Check minimum data requirements per feature category
    temporal_ok = n_obs >= MIN_OBSERVATIONS["temporal_features"]
    intensity_ok = n_obs >= MIN_OBSERVATIONS["intensity_features"]
    spatial_ok = n_obs >= MIN_OBSERVATIONS["spatial_features"]
    persistence_ok = n_obs >= MIN_OBSERVATIONS["persistence_features"]

    # Determine overall baseline status
    if n_obs >= 3:
        baseline_status = BASELINE_STATUS["SUFFICIENT"]
    elif n_obs >= 1:
        baseline_status = BASELINE_STATUS["INSUFFICIENT"]
    else:
        baseline_status = BASELINE_STATUS["NO_DATA"]

    profile = {
        "event_id": event_id,
        "observation_count": n_obs,
        "baseline_status": baseline_status,
        "data_quality": _compute_data_quality(observations),
    }

    # A. TEMPORAL FEATURES (requires >= 2 observations)
    if temporal_ok:
        profile["temporal_features"] = _compute_temporal_features(observations)
    else:
        profile["temporal_features"] = _insufficient("temporal_features")

    # B. INTENSITY FEATURES (requires >= 1 observation)
    if intensity_ok:
        profile["intensity_features"] = _compute_intensity_features(observations)
    else:
        profile["intensity_features"] = _insufficient("intensity_features")

    # C. SPATIAL FEATURES (requires >= 2 observations)
    if spatial_ok:
        profile["spatial_features"] = _compute_spatial_features(observations)
    else:
        profile["spatial_features"] = _insufficient("spatial_features")

    # D. PERSISTENCE FEATURES (requires >= 2 observations)
    if persistence_ok:
        profile["persistence_features"] = _compute_persistence_features(observations)
    else:
        profile["persistence_features"] = _insufficient("persistence_features")

    # E. DATA QUALITY (requires >= 1 observation)
    profile["data_quality"] = _compute_data_quality(observations)

    return profile


def _insufficient(feature_name: str) -> Dict[str, Any]:
    """Return INSUFFICIENT_DATA sentinel for a feature."""
    return {
        "status": "INSUFFICIENT_DATA",
        "feature": feature_name,
        "note": f"Insufficient observations for {feature_name}. Minimum {MIN_OBSERVATIONS[feature_name]} required.",
    }


def _insufficient_data_quality(obs_count: int) -> Dict[str, Any]:
    """Return data quality metrics with honest status."""
    return {
        "observation_count": obs_count,
        "status": BASELINE_STATUS["NO_DATA"] if obs_count == 0 else BASELINE_STATUS["INSUFFICIENT"],
        "confidence_distribution": None,
        "source_distribution": None,
        "completeness": 0.0,
    }


def _compute_temporal_features(observations: List[ThermalObservation]) -> Dict[str, Any]:
    """Compute temporal features from observations."""
    timestamps = sorted([o.timestamp for o in observations if o.timestamp is not None])

    if not timestamps:
        return {"status": "INSUFFICIENT_DATA", "note": "No valid timestamps"}

    first_detection = timestamps[0]
    last_detection = timestamps[-1]
    duration = (last_detection - first_detection).total_seconds() / 3600.0  # hours
    active_days = len(set(ts.date() for ts in timestamps))
    detection_frequency = len(timestamps) / max(active_days, 1)

    # Recurrence: count distinct dates with detections
    recurrence = len(set(ts.date() for ts in timestamps))

    # Temporal trend (based on intensity over time)
    trend = "UNKNOWN"
    if len(timestamps) >= 2:
        intensities = [o.intensity for o in observations if o.intensity is not None]
        if len(intensities) >= 2:
            first_half = intensities[:len(intensities)//2]
            second_half = intensities[len(intensities)//2:]
            if first_half and second_half:
                first_avg = np.mean(first_half)
                second_avg = np.mean(second_half)
                diff = second_avg - first_avg
                threshold = abs(first_avg) * 0.1 if first_avg != 0 else 1.0
                if diff > threshold:
                    trend = "INCREASING"
                elif diff < -threshold:
                    trend = "DECREASING"
                else:
                    trend = "STABLE"

    return {
        "first_detection": first_detection.isoformat(),
        "last_detection": last_detection.isoformat(),
        "active_days": active_days,
        "event_duration_hours": round(duration, 2),
        "detection_frequency": round(detection_frequency, 2),  # detections per active day
        "recurrence": recurrence,  # distinct days with detections
        "temporal_trend": trend,
    }


def _compute_intensity_features(observations: List[ThermalObservation]) -> Dict[str, Any]:
    """Compute intensity features from observations."""
    intensities = [o.intensity for o in observations if o.intensity is not None]

    if not intensities:
        return {
            "status": "INSUFFICIENT_DATA",
            "note": "No intensity data available",
            "mean_brightness_temperature": None,
            "max_brightness_temperature": None,
            "min_brightness_temperature": None,
            "intensity_variance": None,
            "intensity_trend": None,
            "frp_statistics": None,
        }

    mean_intensity = float(np.mean(intensities))
    max_intensity = float(np.max(intensities))
    min_intensity = float(np.min(intensities))
    variance = float(np.var(intensities))

    # Intensity trend
    intensity_trend = "UNKNOWN"
    if len(intensities) >= 2:
        first_half = intensities[:len(intensities)//2]
        second_half = intensities[len(intensities)//2:]
        first_avg = np.mean(first_half)
        second_avg = np.mean(second_half)
        diff = second_avg - first_avg
        threshold = abs(first_avg) * 0.1 if first_avg != 0 else 1.0
        if diff > threshold:
            intensity_trend = "INCREASING"
        elif diff < -threshold:
            intensity_trend = "DECREASING"
        else:
            intensity_trend = "STABLE"

    # FRP statistics (if available in metadata)
    frp_values = []
    for o in observations:
        if o.metadata_json and isinstance(o.metadata_json, dict):
            frp = o.metadata_json.get("frp")
            if frp is not None:
                try:
                    frp_values.append(float(frp))
                except (ValueError, TypeError):
                    pass

    frp_stats = None
    if frp_values:
        frp_stats = {
            "mean": round(float(np.mean(frp_values)), 2),
            "max": round(float(np.max(frp_values)), 2),
            "min": round(float(np.min(frp_values)), 2),
        }

    return {
        "mean_brightness_temperature": round(mean_intensity, 2),
        "max_brightness_temperature": round(max_intensity, 2),
        "min_brightness_temperature": round(min_intensity, 2),
        "intensity_variance": round(variance, 2),
        "intensity_trend": intensity_trend,
        "frp_statistics": frp_stats,
    }


def _compute_spatial_features(observations: List[ThermalObservation]) -> Dict[str, Any]:
    """Compute spatial features from observations."""
    lats = [o.latitude for o in observations if o.latitude is not None]
    lons = [o.longitude for o in observations if o.longitude is not None]

    if not lats or not lons or len(lats) < 2 or len(lons) < 2:
        return {"status": "INSUFFICIENT_DATA", "note": "Need at least 2 observations with coordinates"}

    centroid_lat = float(np.mean(lats))
    centroid_lon = float(np.mean(lons))

    # Spatial spread (bounding box area in degrees)
    lat_range = max(lats) - min(lats)
    lon_range = max(lons) - min(lons)
    spatial_spread = lat_range * lon_range

    # Spatial variance
    spatial_variance = float(np.var(lats) + np.var(lons))

    # Spatial stability (inverse of spatial variance - higher = more stable)
    spatial_stability = 1.0 / (1.0 + spatial_variance) if spatial_variance > 0 else 1.0

    # Number of spatially distinct detections (unique lat/lon pairs rounded)
    distinct_coords = set()
    for lat, lon in zip(lats, lons):
        distinct_coords.add((round(lat, 3), round(lon, 3)))
    distinct_detections = len(distinct_coords)

    return {
        "centroid_lat": round(centroid_lat, 4),
        "centroid_lon": round(centroid_lon, 4),
        "spatial_spread": round(spatial_spread, 4),
        "spatial_variance": round(spatial_variance, 4),
        "spatial_stability": round(spatial_stability, 4),
        "distinct_detections": distinct_detections,
    }


def _compute_persistence_features(observations: List[ThermalObservation]) -> Dict[str, Any]:
    """Compute persistence features from observations."""
    timestamps = sorted([o.timestamp for o in observations if o.timestamp is not None])

    if not timestamps or len(timestamps) < 2:
        return {"status": "INSUFFICIENT_DATA", "note": "Need at least 2 observations with timestamps"}

    # Distinct calendar days with detections
    active_dates = sorted(set(ts.date() for ts in timestamps))
    consecutive_days = _count_consecutive_days(active_dates)

    # Persistence type classification
    if len(active_dates) >= 3 and consecutive_days >= 2:
        persistence_type = "PERSISTENT"
    elif len(active_dates) >= 2:
        persistence_type = "RECURRING"
    else:
        persistence_type = "ONE_OFF"

    # Persistence score (detections per active day)
    persistence_score = len(timestamps) / max(len(active_dates), 1)

    return {
        "total_detections": len(timestamps),
        "active_days": len(active_dates),
        "consecutive_active_days": consecutive_days,
        "persistence_score": round(persistence_score, 2),
        "persistence_type": persistence_type,
        "recurrence_frequency": round(persistence_score, 2),  # same as detections per active day
        "detection_pattern": "persistent" if persistence_type == "PERSISTENT" else "intermittent" if persistence_type == "RECURRING" else "one-off",
    }


def _count_consecutive_days(dates: List) -> int:
    """Count maximum consecutive days in a list of dates."""
    if not dates:
        return 0

    date_set = set(dates)
    max_consecutive = 1

    for d in dates:
        count = 1
        next_day = d
        while True:
            next_day = next_day + timedelta(days=1)
            if next_day in date_set:
                count += 1
            else:
                break
        max_consecutive = max(max_consecutive, count)

    return max_consecutive


def _compute_data_quality(observations: List[ThermalObservation]) -> Dict[str, Any]:
    """Compute data quality metrics."""
    n_obs = len(observations)

    if n_obs == 0:
        return {"status": BASELINE_STATUS["NO_DATA"], "completeness": 0.0}

    # Confidence distribution
    confidences = [o.confidence for o in observations]
    conf_dist = {
        "mean": round(float(np.mean([c for c in confidences if c is not None])), 2) if any(c is not None for c in confidences) else None,
        "low": sum(1 for c in confidences if c is not None and c < 50),
        "medium": sum(1 for c in confidences if c is not None and 50 <= c < 80),
        "high": sum(1 for c in confidences if c is not None and c >= 80),
        "null": sum(1 for c in confidences if c is None),
    }

    # Source distribution
    sources = [o.source for o in observations]
    source_counts = Counter(sources)
    source_dist = {source: count for source, count in source_counts.items()}

    # Completeness: fraction of observations with all critical fields
    complete_obs = sum(
        1 for o in observations
        if o.latitude is not None and o.longitude is not None and o.timestamp is not None
    )
    completeness = complete_obs / n_obs

    return {
        "observation_count": n_obs,
        "completeness": round(completeness, 2),  # 0-1 fraction
        "confidence_distribution": conf_dist,
        "source_distribution": source_dist,
        "status": BASELINE_STATUS["SUFFICIENT"] if completeness >= 0.9 else BASELINE_STATUS["INSUFFICIENT"],
    }


def compute_location_specific_statistics(
    db: Session,
    lat: float,
    lon: float,
    radius_km: float = 50.0,
) -> Dict[str, Any]:
    """Compute statistics for a geographic location.

    Uses PostGIS spatial query to find observations within radius.
    Falls back to bounding box if PostGIS not available.

    Args:
        db: Database session (optional - if None, returns no-data status)
        lat: Center latitude
        lon: Center longitude
        radius_km: Search radius in kilometers

    Returns:
        Location-specific statistics dictionary
    """
    if db is None:
        return {"status": BASELINE_STATUS["NO_DATA"], "observation_count": 0, "note": "No database session"}

    # Bounding box for approximate spatial filter
    lat_range = radius_km / 111.0  # ~111 km per degree latitude
    lon_range = radius_km / (111.0 * np.cos(np.radians(lat)))

    nearby_observations = db.query(ThermalObservation).filter(
        ThermalObservation.latitude >= lat - lat_range,
        ThermalObservation.latitude <= lat + lat_range,
        ThermalObservation.longitude >= lon - lon_range,
        ThermalObservation.longitude <= lon + lon_range,
    ).all()

    if not nearby_observations:
        return {
            "status": BASELINE_STATUS["NO_DATA"],
            "note": "No observations found in this location",
            "observation_count": 0,
        }

    # Compute basic statistics
    timestamps = [o.timestamp for o in nearby_observations if o.timestamp is not None]
    intensities = [o.intensity for o in nearby_observations if o.intensity is not None]

    stats = {
        "observation_count": len(nearby_observations),
        "unique_days": len(set(ts.date() for ts in timestamps)) if timestamps else 0,
        "date_range": {
            "start": min(timestamps).isoformat() if timestamps else None,
            "end": max(timestamps).isoformat() if timestamps else None,
        },
    }

    if intensities:
        stats["intensity"] = {
            "mean": round(float(np.mean(intensities)), 2),
            "max": round(float(np.max(intensities)), 2),
            "min": round(float(np.min(intensities)), 2),
            "std": round(float(np.std(intensities)), 2),
        }

    # Activity by hour of day (to identify recurring patterns)
    hours = [ts.hour for ts in timestamps]
    if hours:
        hour_counts = Counter(hours)
        stats["peak_hour"] = hour_counts.most_common(1)[0][0]
        stats["hourly_distribution"] = dict(hour_counts)

    # Activity by day of week
    days = [ts.strftime("%A") for ts in timestamps]
    if days:
        day_counts = Counter(days)
        stats["peak_day"] = day_counts.most_common(1)[0][0]
        stats["daily_distribution"] = dict(day_counts)

    # Source distribution
    sources = Counter([o.source for o in nearby_observations])
    stats["source_distribution"] = dict(sources)

    # Determine if sufficient for baseline
    stats["baseline_status"] = (
        BASELINE_STATUS["SUFFICIENT"] if len(nearby_observations) >= 5
        else BASELINE_STATUS["INSUFFICIENT"] if len(nearby_observations) >= 2
        else BASELINE_STATUS["NO_DATA"]
    )

    return stats


def compute_historical_statistics(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compute historical thermal statistics.

    Aggregates observations and events across time periods.

    Args:
        db: Database session (optional - if None, returns no-data status)
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        Historical statistics dictionary
    """
    if db is None:
        return {"status": BASELINE_STATUS["NO_DATA"], "observation_count": 0, "note": "No database session"}

    query = db.query(ThermalObservation)
    if start_date:
        query = query.filter(ThermalObservation.timestamp >= start_date)
    if end_date:
        query = query.filter(ThermalObservation.timestamp < end_date)

    observations = query.all()

    if not observations:
        return {"status": BASELINE_STATUS["NO_DATA"], "note": "No observations found"}

    # Daily activity
    daily_counts = Counter(o.timestamp.date() for o in observations if o.timestamp)

    # Weekly activity
    weekly_counts = Counter(o.timestamp.isocalendar()[1] for o in observations if o.timestamp)

    # Monthly activity
    monthly_counts = Counter(o.timestamp.month for o in observations if o.timestamp)

    # Intensity distribution
    intensities = [o.intensity for o in observations if o.intensity is not None]
    intensity_dist = {
        "mean": round(float(np.mean(intensities)), 2) if intensities else None,
        "median": round(float(np.median(intensities)), 2) if intensities else None,
        "std": round(float(np.std(intensities)), 2) if len(intensities) > 1 else None,
        "min": round(float(np.min(intensities)), 2) if intensities else None,
        "max": round(float(np.max(intensities)), 2) if intensities else None,
        "q25": round(float(np.percentile(intensities, 25)), 2) if intensities else None,
        "q75": round(float(np.percentile(intensities, 75)), 2) if intensities else None,
    } if intensities else None

    # Detection frequency (observations per day)
    unique_days = len(set(o.timestamp.date() for o in observations if o.timestamp))
    detection_frequency = len(observations) / max(unique_days, 1)

    # Duration distributions (for events)
    events_query = db.query(ThermalEvent)
    if start_date:
        events_query = events_query.filter(ThermalEvent.start_time >= start_date)
    if end_date:
        events_query = events_query.filter(ThermalEvent.start_time < end_date)

    events = events_query.all()
    event_durations = []
    for event in events:
        if event.start_time and event.end_time:
            duration = (event.end_time - event.start_time).total_seconds() / 3600.0
            event_durations.append(duration)

    duration_dist = {
        "mean": round(float(np.mean(event_durations)), 2) if event_durations else None,
        "median": round(float(np.median(event_durations)), 2) if event_durations else None,
        "std": round(float(np.std(event_durations)), 2) if len(event_durations) > 1 else None,
    } if event_durations else None

    # Spatial behavior
    lats = [o.latitude for o in observations if o.latitude is not None]
    lons = [o.longitude for o in observations if o.longitude is not None]
    spatial_behavior = {
        "lat_range": [min(lats), max(lats)] if lats else None,
        "lon_range": [min(lons), max(lons)] if lons else None,
        "centroid": [float(np.mean(lats)), float(np.mean(lons))] if lats and lons else None,
        "total_observations": len(observations),
    } if lats and lons else None

    # Temporal behavior
    temporal_behavior = {
        "detection_frequency": round(detection_frequency, 2),
        "peak_hour": Counter(ts.hour for ts in [o.timestamp for o in observations if o.timestamp]).most_common(1)[0][0] if any(o.timestamp for o in observations) else None,
        "peak_day": Counter(ts.strftime("%A") for ts in [o.timestamp for o in observations if o.timestamp]).most_common(1)[0][0] if any(o.timestamp for o in observations) else None,
        "unique_days": unique_days,
    }

    return {
        "status": BASELINE_STATUS["SUFFICIENT"] if len(observations) >= 10 else BASELINE_STATUS["INSUFFICIENT"],
        "observation_count": len(observations),
        "event_count": len(events),
        "daily_activity": {str(k): v for k, v in sorted(daily_counts.items())},
        "weekly_activity": dict(weekly_counts),
        "monthly_activity": dict(monthly_counts),
        "intensity_distribution": intensity_dist,
        "detection_frequency": round(detection_frequency, 2),
        "duration_distribution": duration_dist,
        "spatial_behavior": spatial_behavior,
        "temporal_behavior": temporal_behavior,
        "source_distribution": dict(Counter([o.source for o in observations])),
        "confidence_distribution": dict(Counter([str(o.confidence) for o in observations])),
    }


def compute_baseline(
    db: Session,
    lat: float,
    lon: float,
    radius_km: float = 50.0,
) -> Dict[str, Any]:
    """Compute location-specific historical baseline.

    Calculates expected thermal behavior for a location based on
    historical observations. Uses statistically defensible methods
    appropriate to the amount of data available.

    Args:
        db: Database session
        lat: Location latitude
        lon: Location longitude
        radius_km: Search radius in kilometers

    Returns:
        Baseline dictionary with expected values and data sufficiency status
    """
    stats = compute_location_specific_statistics(db, lat, lon, radius_km)

    if stats.get("status") == BASELINE_STATUS["NO_DATA"]:
        return {
            "status": BASELINE_STATUS["NO_DATA"],
            "baseline": None,
            "note": "No historical observations found for this location",
            "data_required": "At least 2 observations within 50km radius",
        }

    if stats.get("status") == BASELINE_STATUS["INSUFFICIENT"]:
        return {
            "status": BASELINE_STATUS["INSUFFICIENT"],
            "baseline": _compute_partial_baseline(stats),
            "note": "Insufficient data for confident baseline",
            "data_required": "At least 5 observations for reliable baseline",
            "current_data": stats.get("observation_count", 0),
        }

    # SUFFICIENT_HISTORY - compute full baseline
    baseline = _compute_full_baseline(stats)

    return {
        "status": BASELINE_STATUS["SUFFICIENT"],
        "baseline": baseline,
        "note": "Baseline computed from sufficient historical data",
        "data_required": None,
    }


def _compute_full_baseline(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Compute full baseline from sufficient statistics."""
    baseline = {
        "expected_detection_frequency": stats.get("detection_frequency"),
        "expected_intensity_range": {
            "min": stats.get("intensity", {}).get("min"),
            "max": stats.get("intensity", {}).get("max"),
            "mean": stats.get("intensity", {}).get("mean"),
        } if stats.get("intensity") else None,
        "expected_recurrence": stats.get("unique_days"),
        "expected_duration": stats.get("duration_distribution", {}).get("mean"),
        "expected_spatial_behavior": stats.get("spatial_behavior", {}).get("centroid"),
        "expected_temporal_activity": {
            "peak_hour": stats.get("peak_hour"),
            "peak_day": stats.get("peak_day"),
        },
    }
    return baseline


def _compute_partial_baseline(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Compute partial baseline from insufficient statistics."""
    baseline = {
        "observation_count": stats.get("observation_count"),
        "unique_days": stats.get("unique_days"),
        "intensity": stats.get("intensity"),
        "source_distribution": stats.get("source_distribution"),
        "temporal_activity": {
            "peak_hour": stats.get("peak_hour"),
            "peak_day": stats.get("peak_day"),
        },
    }
    return baseline


def compare_current_vs_baseline(
    current_observations: List[ThermalObservation],
    baseline: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare current thermal behavior against historical baseline.

    Calculates defensible deviation metrics where sufficient history exists.

    Args:
        current_observations: Current observations to compare
        baseline: Historical baseline dictionary

    Returns:
        Comparison result with deviation metrics and status
    """
    if not current_observations:
        return {
            "status": "NO_DATA",
            "note": "No current observations to compare",
            "deviations": None,
        }

    if not baseline or baseline.get("status") in (BASELINE_STATUS["NO_DATA"], "NO_HISTORY"):
        return {
            "status": "INSUFFICIENT_HISTORY",
            "note": "No historical baseline available for comparison",
            "deviations": None,
        }

    current_intensities = [o.intensity for o in current_observations if o.intensity is not None]
    current_count = len(current_observations)

    deviations = {}

    # Frequency deviation
    baseline_freq = baseline.get("baseline", {}).get("expected_detection_frequency")
    if baseline_freq is not None:
        deviations["frequency_deviation"] = {
            "current": current_count,
            "baseline": baseline_freq,
            "deviation_pct": round(((current_count - baseline_freq) / baseline_freq * 100), 1) if baseline_freq > 0 else None,
            "status": "elevated" if current_count > baseline_freq * 1.5 else "normal" if current_count >= baseline_freq * 0.5 else "below_baseline",
        }

    # Intensity deviation
    baseline_intensity = baseline.get("baseline", {}).get("expected_intensity_range", {}).get("mean")
    if baseline_intensity and current_intensities:
        current_mean = float(np.mean(current_intensities))
        deviations["intensity_deviation"] = {
            "current_mean": round(current_mean, 2),
            "baseline_mean": baseline_intensity,
            "deviation_k": round(current_mean - baseline_intensity, 2),
            "deviation_pct": round(((current_mean - baseline_intensity) / baseline_intensity * 100), 1) if baseline_intensity > 0 else None,
            "status": "elevated" if current_mean > baseline_intensity + 10 else "normal" if current_mean >= baseline_intensity - 10 else "below_baseline",
        }

    # Duration deviation
    baseline_duration = baseline.get("baseline", {}).get("expected_duration")
    if baseline_duration is not None:
        # Estimate current duration from observations
        timestamps = sorted([o.timestamp for o in current_observations if o.timestamp is not None])
        if len(timestamps) >= 2:
            current_duration = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
            deviations["duration_deviation"] = {
                "current_hours": round(current_duration, 2),
                "baseline_hours": baseline_duration,
                "deviation_pct": round(((current_duration - baseline_duration) / baseline_duration * 100), 1) if baseline_duration > 0 else None,
                "status": "elevated" if current_duration > baseline_duration * 1.5 else "normal" if current_duration >= baseline_duration * 0.5 else "below_baseline",
            }

    # Determine overall status
    elevated_count = sum(1 for d in deviations.values() if d.get("status") == "elevated")

    if elevated_count > 0:
        overall_status = "ELEVATED_RELATIVE_TO_BASELINE"
    elif deviations:
        overall_status = "NORMAL"
    else:
        overall_status = "INSUFFICIENT_DATA"

    return {
        "status": overall_status,
        "note": f"Current behavior is {overall_status.replace('_', ' ').lower()}" if overall_status != "INSUFFICIENT_DATA" else "Insufficient data for comparison",
        "deviations": deviations,
        "is_ml": False,
        "methodology": "Statistical baseline comparison (not ML anomaly detection)",
    }
"""Persistent thermal-source detection.

Identifies locations that repeatedly generate thermal detections over time.

Metrics tracked:
  - Number of detections (observation count)
  - Number of active days
  - Persistence score (detections / active_days)
  - Average thermal intensity
  - Intensity variation (std dev)
  - Spatial stability (centroid drift variance)
  - Long-term trend (increasing / decreasing / stable)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np

from app.config import settings
from app.db.models import ThermalObservation, ThermalEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persistence scoring
# ---------------------------------------------------------------------------

def compute_persistence_score(
    observations: List[Any],
) -> Dict[str, Any]:
    """Compute persistence metrics for a set of observations.

    Accepts either ThermalObservation ORM objects or dict-like observations.

    Returns a dict with:
    - total_detections: int
    - active_days: int (number of distinct calendar days with ≥1 detection)
    - persistence_score: float (detections / active_days, 0 if no days)
    - average_intensity: float or None
    - intensity_variance: float or None
    - spatial_stability: float (variance of centroid; lower = more stable)
    - first_detection: datetime or None
    - last_detection: datetime or None
    - trend: str ("INCREASING" | "DECREASING" | "STABLE" | "UNKNOWN")
    """

    if not observations:
        return {
            "total_detections": 0,
            "active_days": 0,
            "persistence_score": 0.0,
            "average_intensity": None,
            "intensity_variance": None,
            "spatial_stability": None,
            "first_detection": None,
            "last_detection": None,
            "trend": "UNKNOWN",
        }

    # Helper to extract values from dict or ORM object
    def get_attr(obj, attr_name, default=None):
        if isinstance(obj, dict):
            return obj.get(attr_name, default)
        else:
            # Assume ORM object or similar
            return getattr(obj, attr_name, default)

    # Basic counts
    total_detections = len(observations)

    # Distinct calendar days with at least one detection
    detection_dates = set()
    for obs in observations:
        ts = get_attr(obs, "timestamp")
        if ts:
            # Convert to datetime if needed
            if isinstance(ts, str):
                try:
                    from datetime import datetime
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except:
                    pass
            if hasattr(ts, "date"):
                detection_dates.add(ts.date())
    active_days = len(detection_dates)

    # Persistence score: detections per active day
    persistence_score = float(total_detections) / max(active_days, 1)

    # Average intensity (only observations with a value)
    intensities = [get_attr(obs, "intensity") for obs in observations if get_attr(obs, "intensity") is not None]
    if intensities:
        average_intensity = float(np.mean(intensities))
        intensity_variance = float(np.var(intensities))
    else:
        average_intensity = None
        intensity_variance = None

    # Spatial stability: variance of centroid positions
    lats = [get_attr(obs, "latitude") for obs in observations if get_attr(obs, "latitude") is not None]
    lons = [get_attr(obs, "longitude") for obs in observations if get_attr(obs, "longitude") is not None]
    if len(lats) > 1:
        spatial_stability = float(np.var(lats) + np.var(lons))
    else:
        spatial_stability = None

    # First / last detection timestamps
    valid_obs_with_ts = [obs for obs in observations if get_attr(obs, "timestamp") is not None]
    if valid_obs_with_ts:
        first_detection = min(valid_obs_with_ts, key=lambda o: get_attr(o, "timestamp"))
        last_detection = max(valid_obs_with_ts, key=lambda o: get_attr(o, "timestamp"))
        # Extract timestamps from the objects
        first_detection = get_attr(first_detection, "timestamp")
        last_detection = get_attr(last_detection, "timestamp")
    else:
        first_detection = None
        last_detection = None

    # Trend determination (simple: compare first-half vs second-half intensity)
    trend = _determine_trend(valid_obs_with_ts)

    return {
        "total_detections": total_detections,
        "active_days": active_days,
        "persistence_score": round(persistence_score, 2),
        "average_intensity": round(average_intensity, 2) if average_intensity is not None else None,
        "intensity_variance": round(intensity_variance, 2) if intensity_variance is not None else None,
        "spatial_stability": round(spatial_stability, 8) if spatial_stability is not None else None,
        "first_detection": first_detection,
        "last_detection": last_detection,
        "trend": trend,
    }


def _determine_trend(observations: List[Any]) -> str:
    """Heuristic trend detection based on temporal intensity pattern.

    Compares the first half of the observation period's average intensity
    against the second half. Returns one of: INCREASING, DECREASING, STABLE, UNKNOWN.
    """
    if not observations or len(observations) < 3:
        return "UNKNOWN"

    # Helper to extract values from dict or ORM object
    def get_attr(obj, attr_name, default=None):
        if isinstance(obj, dict):
            return obj.get(attr_name, default)
        else:
            return getattr(obj, attr_name, default)

    # Sort by timestamp
    valid_obs = [o for o in observations if get_attr(o, "timestamp") is not None]
    sorted_obs = sorted(valid_obs, key=lambda o: get_attr(o, "timestamp"))

    n = len(sorted_obs)
    half = n // 2

    if half < 2:
        return "UNKNOWN"

    first_half = sorted_obs[:half]
    second_half = sorted_obs[half:]

    first_values = [get_attr(o, "intensity") for o in first_half if get_attr(o, "intensity") is not None]
    second_values = [get_attr(o, "intensity") for o in second_half if get_attr(o, "intensity") is not None]
    if not first_values or not second_values:
        return "UNKNOWN"
    first_avg = np.mean(first_values)
    second_avg = np.mean(second_values)

    diff = second_avg - first_avg

    # Use a threshold: if difference is > 10% of first half average, it's a trend
    threshold = abs(first_avg) * 0.1 if first_avg != 0 else 1.0

    if diff > threshold:
        return "INCREASING"
    elif diff < -threshold:
        return "DECREASING"
    else:
        return "STABLE"


# ---------------------------------------------------------------------------
# Persistent-source detection across events
# ---------------------------------------------------------------------------

def detect_persistent_sources(
    events: List[Dict[str, Any]],
    min_detections: int = settings.PERSISTENCE_MIN_DETECTIONS,
) -> List[Dict[str, Any]]:
    """Filter detected events to identify persistent thermal sources.

    A "persistent thermal source" is an event that has generated at least
    `min_detections` within the ingestion window.

    Parameters
    ----------
    events : list[dict]
        Output from `clustering.cluster_observations()`.
    min_detections : int
        Minimum observation count to qualify as persistent.

    Returns
    -------
    list[dict]
        Persistent-source events with enriched metrics.
    """
    persistent: List[Dict[str, Any]] = []

    for event in events:
        count = event.get("observation_count", 0)
        if count >= min_detections:
            # Enrich the event with persistence-specific data
            enriched = dict(event)
            enriched["persistence_type"] = "CONFIRMED"
            enriched["persistence_score"] = count  # raw count as score
            enriched["active_days_estimate"] = max(1, int(count / 2))  # rough estimate
            persistent.append(enriched)
        else:
            # Low-count event — still record but mark as temporary
            event["persistence_type"] = "TEMPORARY"
            event["persistence_score"] = count

    logger.info(
        "Persistent sources: %d out of %d events (min_detections=%d)",
        len(persistent),
        len(events),
        min_detections,
    )

    return persistent

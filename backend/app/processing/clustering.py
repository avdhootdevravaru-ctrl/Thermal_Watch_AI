"""Spatial-temporal thermal-event clustering.

Groups individual FIRMS observations into meaningful thermal events using
a fast grid-hash clustering approach. Observations within the same spatial
grid cell (configurable size) and time window are grouped into one event.

This is O(n) and suitable for thousands to millions of observations,
avoiding the O(n²) distance matrix computation of naive DBSCAN.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


def obs_to_point(obs: Dict[str, Any]) -> Optional[np.ndarray]:
    """Convert a normalized observation dict to a 4D point.

    Returns None if the observation cannot be converted.
    """
    try:
        lat = float(obs.get("latitude") or 0)
        lon = float(obs.get("longitude") or 0)
        ts = obs.get("timestamp")
        if ts is None:
            return None

        if isinstance(ts, str):
            from dateutil.parser import parse as parse_dt
            ts = parse_dt(ts)
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        hour = ts.hour
        window_start = _ingestion_window_start()
        day_idx = (ts - window_start).days

        return np.array([lat, lon, hour, day_idx], dtype=np.float64)
    except Exception:
        return None


def _ingestion_window_start() -> datetime:
    """Return the start of the FIRMS look-back window."""
    days_ago = max(1, settings.FIRMS_DAYS)
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def cluster_observations(
    observations: List[Dict[str, Any]],
    distance_meters: float = settings.CLUSTER_DISTANCE_METERS,
    time_hours: float = settings.CLUSTER_TIME_HOURS,
) -> List[Dict[str, Any]]:
    """Fast spatial-temporal clustering using grid hash + union-find.

    Algorithm:
      1. Compute a grid cell for each observation: (lat_cell, lon_cell, time_cell)
         where cell size ≈ distance_meters / time_hours.
      2. Observations in adjacent cells (within 1 cell in each dimension) are linked.
      3. Union-Find merges all connected cells into events.

    Complexity: O(n α(n)) where α is the inverse Ackermann function (practically constant).

    Parameters
    ----------
    observations : list[dict]
        Normalized observation dicts.
    distance_meters : float
        Maximum distance in meters for spatial clustering.
    time_hours : float
        Maximum time gap in hours for clustering.

    Returns
    -------
    list[dict]
        One dict per detected event.
    """
    if not observations:
        return []

    # Parse timestamps and filter valid observations
    def parse_ts(ts: Any) -> Optional[datetime]:
        try:
            if isinstance(ts, str):
                from dateutil.parser import parse as parse_dt
                ts = parse_dt(ts)
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts
        except Exception:
            return None

    parsed = []
    for obs in observations:
        lat = obs.get("latitude")
        lon = obs.get("longitude")
        ts = parse_ts(obs.get("timestamp"))
        if lat is not None and lon is not None and ts is not None:
            parsed.append((obs, lat, lon, ts))

    if not parsed:
        return []

    # Grid cell size in degrees
    # At the equator: 1 degree lat ≈ 111 km, 1 degree lon ≈ 111 km
    # Use the median latitude for lon scaling
    lats = [p[1] for p in parsed]
    median_lat = float(np.median(lats))
    lat_bin_deg = distance_meters / 111_000.0
    lon_bin_deg = distance_meters / (111_000.0 * max(np.cos(np.radians(median_lat)), 0.1))
    time_bin_hours = max(time_hours, 1.0)

    # Compute base time (midnight of the earliest observation's day in UTC)
    all_times = [p[3] for p in parsed]
    base_date = datetime.fromordinal(min(t.toordinal() for t in all_times))
    base_time = base_date.replace(tzinfo=timezone.utc)

    # Union-Find data structure
    n = len(parsed)
    parent = list(range(n))
    rank = [0] * n

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px == py:
            return
        if rank[px] < rank[py]:
            px, py = py, px
        parent[py] = px
        if rank[px] == rank[py]:
            rank[px] += 1

    # Build spatial hash map: cell_key -> list of observation indices
    cell_map: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)

    for i, (_, lat, lon, ts) in enumerate(parsed):
        lat_cell = int(round(lat / lat_bin_deg))
        lon_cell = int(round(lon / lon_bin_deg))
        time_cell = int(round((ts - base_time).total_seconds() / 3600.0 / time_bin_hours))
        cell_map[(lat_cell, lon_cell, time_cell)].append(i)

    # Link observations in neighboring cells
    for (lc, rc, tc), indices in cell_map.items():
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for dk in (-1, 0, 1):
                    neighbor_key = (lc + di, rc + dj, tc + dk)
                    if neighbor_key in cell_map:
                        for i in indices:
                            for j in cell_map[neighbor_key]:
                                if i != j:
                                    union(i, j)

    # Group by connected component
    comp_to_indices: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        comp_to_indices[find(i)].append(i)

    # Build event summaries
    events: List[Dict[str, Any]] = []
    for comp_id, idx_list in comp_to_indices.items():
        if not idx_list:
            continue

        obs_list = [parsed[i][0] for i in idx_list]
        lats_c = [parsed[i][1] for i in idx_list]
        lons_c = [parsed[i][2] for i in idx_list]
        times_c = [parsed[i][3] for i in idx_list]

        centroid_lat = float(np.mean(lats_c))
        centroid_lon = float(np.mean(lons_c))
        start_time = min(times_c)
        end_time = max(times_c)

        events.append({
            "centroid_lat": centroid_lat,
            "centroid_lon": centroid_lon,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "observation_count": len(idx_list),
            "observation_indices": idx_list,
        })

    logger.info(
        "Union-Find clustering: %d observations -> %d events",
        n, len(events),
    )
    return events


def assign_observations_to_events(
    observations: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Attach an `event_id` to each observation based on clustering results."""
    valid_to_event: Dict[int, int] = {}
    for event_idx, event in enumerate(events):
        for valid_idx in event.get("observation_indices", []):
            valid_to_event[valid_idx] = event_idx + 1

    result = []
    for o_idx, obs in enumerate(observations):
        obs_with_event = dict(obs)
        obs_with_event["event_id"] = valid_to_event.get(o_idx)
        result.append(obs_with_event)

    return result

"""Read-only local replay of real FIRMS observations when PostGIS is absent.

The file contains the unmodified NASA CSV response.  Every request uses the
same validation, clustering, persistence, Thermal DNA and risk functions as
the PostgreSQL path.  The capture is labelled with its actual acquisition
window; it is never described as a continuously connected live database.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from app.config import settings
from app.ingestion.validation import validate_firms_csv
from app.ml.classifier import classify_with_fallback
from app.processing.clustering import cluster_observations
from app.processing.persistence import compute_persistence_score
from app.processing.risk import classify_event, compute_risk_score


@lru_cache(maxsize=1)
def snapshot_state() -> dict:
    path = Path(settings.FIRMS_SNAPSHOT_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"FIRMS snapshot missing: {path}")
    raw = path.read_text(encoding="utf-8-sig")
    metadata_path = path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    source = metadata.get("source", settings.FIRMS_SATELLITE)
    accepted, report = validate_firms_csv(raw, source=source)
    capture_time = metadata.get("captured_at")
    if capture_time is None:
        capture_time = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()

    events = {}
    clusters = cluster_observations(
        accepted, distance_meters=settings.CLUSTER_DISTANCE_METERS,
        time_hours=settings.CLUSTER_TIME_HOURS,
    )
    from app.processing.geo_context import resolve_location_name

    now = max((r["timestamp"] for r in accepted), default=datetime.now(timezone.utc))
    for cluster in clusters:
        members = [accepted[index] for index in cluster["observation_indices"]]
        members.sort(key=lambda row: row["timestamp"])
        first = members[0]
        identity = (f"{first['source']}|{first['latitude']:.5f}|"
                    f"{first['longitude']:.5f}|{first['timestamp'].isoformat()}")
        event_id = 100000 + int(hashlib.sha256(identity.encode()).hexdigest()[:8], 16)
        while event_id in events:
            event_id += 1
        observations = [SimpleNamespace(
            id=index + 1, event_id=event_id, timestamp=row["timestamp"],
            latitude=row["latitude"], longitude=row["longitude"],
            intensity=row["intensity"], confidence=row["confidence"],
            confidence_category=row["metadata"].get("confidence_category"),
            source=row["source"], sensor=row["sensor"], metadata_json=row["metadata"],
            frp=row["metadata"].get("frp"),
            satellite=row["metadata"].get("raw_satellite") or row["source"],
            instrument=row["metadata"].get("instrument") or "VIIRS",
            daynight=row["metadata"].get("daynight"),
        ) for index, row in enumerate(members)]
        persistence = compute_persistence_score(observations)
        last = observations[-1].timestamp
        status = ("RESOLVED" if now - last > timedelta(hours=72) else
                  "PERSISTENT" if persistence["active_days"] >= 2
                  and len(observations) >= settings.PERSISTENCE_MIN_DETECTIONS else "ACTIVE")
        obs_dicts = [vars(o) for o in observations]
        classification = classify_with_fallback(obs_dicts, persistence, demo=False)
        risk = compute_risk_score(persistence, classify_event(persistence, obs_dicts), obs_dicts)
        events[event_id] = {
            "id": event_id, "place": resolve_location_name(cluster["centroid_lat"], cluster["centroid_lon"]),
            "latitude": cluster["centroid_lat"], "longitude": cluster["centroid_lon"],
            "start_time": observations[0].timestamp, "end_time": last,
            "observation_count": len(observations),
            "persistence_score": persistence["persistence_score"],
            "status": status, "observations": observations,
            "persistence": persistence, "classification": classification,
            "risk": risk, "data_mode": "FIRMS SNAPSHOT",
        }

    ordered = sorted(events.values(), key=lambda event: (event["risk"]["score"], event["end_time"]), reverse=True)
    return {"events": {event["id"]: event for event in ordered},
            "validation": report.as_dict(), "capture_time": capture_time,
            "source": source, "area": metadata.get("area", settings.FIRMS_AREA),
            "database_persisted": False}


def clear_snapshot_cache() -> None:
    snapshot_state.cache_clear()

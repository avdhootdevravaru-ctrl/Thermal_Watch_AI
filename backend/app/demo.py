"""Read-only local API for synthetic scenarios or a real FIRMS CSV capture.

The same route contracts serve both local providers.  The captured FIRMS path
uses the real validator and clustering pipeline and is always labelled as a
local snapshot; neither provider claims PostgreSQL persistence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from math import cos, radians
from pathlib import Path as FilePath
from types import SimpleNamespace

from fastapi import APIRouter, HTTPException, Path, Query

from app.processing.persistence import compute_persistence_score
from app.processing.risk import classify_event, compute_risk_score
from app.ml.classifier import classify_with_fallback
from app.processing.thermal_profile import compute_thermal_profile
from app.processing.clustering import cluster_observations
from app.config import settings
from app.schemas.event import ThermalEventDetail, ThermalEventList
from app.schemas.map import MapHotspotsResponse
from app.schemas.ingestion import IngestionResult, IngestionRunRequest

router = APIRouter()


def _snapshot_mode() -> bool:
    return not settings.DEMO_MODE and bool(settings.FIRMS_SNAPSHOT_PATH)


def _mode() -> str:
    return "FIRMS SNAPSHOT" if _snapshot_mode() else "DEMO DATA"


def _source() -> str:
    return settings.FIRMS_SATELLITE if _snapshot_mode() else "DEMO_SYNTHETIC"


def _local_status() -> str:
    return "INSUFFICIENT_HISTORY" if _snapshot_mode() else "DEMO_DATA"

# Synthetic scenarios, not observations of these places. IDs are reserved for demo.
# Counts, recency and intensity deliberately vary so existing risk logic produces
# distinct categories without assigning labels by hand.
SCENARIOS = (
    (9001, "Jamshedpur", 22.8046, 86.2029, 24, 8, 382.0, 94.0, 0),
    (9002, "Bhilai", 21.1938, 81.3509, 18, 6, 367.0, 86.0, 0),
    (9003, "Korba", 22.3595, 82.7501, 12, 4, 352.0, 79.0, 0),
    (9004, "Nagpur", 21.1458, 79.0882, 6, 3, 331.0, 72.0, 0),
    (9005, "Surat", 21.1702, 72.8311, 4, 2, 318.0, 61.0, 5),
    (9006, "Hyderabad", 17.3850, 78.4867, 2, 1, 309.0, 52.0, 0),
    (9007, "Patna", 25.5941, 85.1376, 1, 1, 302.0, 43.0, 7),
)


@lru_cache(maxsize=1)
def _events() -> dict[int, dict]:
    if _snapshot_mode():
        from app.snapshot import snapshot_state
        return snapshot_state()["events"]
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    result = {}
    observation_id = 900000
    for event_id, place, lat, lon, count, days, intensity, confidence, last_seen_days_ago in SCENARIOS:
        observations = []
        for i in range(count):
            observation_id += 1
            # Distribute samples across days and a tight spatial footprint.
            age_days = last_seen_days_ago + days - 1 - (i % days)
            timestamp = now - timedelta(days=age_days, hours=(i // days) % 5)
            observations.append(SimpleNamespace(
                id=observation_id,
                event_id=event_id,
                timestamp=timestamp,
                latitude=round(lat + ((i % 5) - 2) * 0.0011, 5),
                longitude=round(lon + ((i % 7) - 3) * 0.0010, 5),
                intensity=round(intensity + (i % 6) * 2.6, 1),
                confidence=min(100.0, confidence + (i % 4) * 1.2),
                source="DEMO_SYNTHETIC",
                sensor="SIMULATED",
                metadata_json={"provenance": "synthetic demo scenario", "frp": round(8 + i * 0.9, 1)},
            ))
        observations.sort(key=lambda o: o.timestamp)
        persistence = compute_persistence_score(observations)
        # Demo lifecycle heuristic: >3 days without a detection is resolved;
        # at least 5 active days and the configured minimum count is persistent.
        status = ("RESOLVED" if (now - observations[-1].timestamp).days > 3
                  else "PERSISTENT" if persistence["active_days"] >= 5
                  and count >= settings.PERSISTENCE_MIN_DETECTIONS else "ACTIVE")
        obs_dicts = [vars(o) for o in observations]
        classification = classify_with_fallback(obs_dicts, persistence, demo=True)
        # Keep operational risk on the established rules, independent of the
        # synthetic weak-label classifier's unvalidated probabilities.
        risk = compute_risk_score(persistence, classify_event(persistence, obs_dicts), obs_dicts)
        result[event_id] = {
            "id": event_id, "place": place, "latitude": lat, "longitude": lon,
            "start_time": observations[0].timestamp,
            "end_time": observations[-1].timestamp,
            "observation_count": count, "persistence_score": persistence["persistence_score"],
            "status": status, "observations": observations, "persistence": persistence,
            "classification": classification, "risk": risk,
            "data_mode": "DEMO DATA",
        }
    # Run the real spatial/temporal clustering code over the demo observations.
    # Keep stable scenario IDs, but fail early if the sample cannot be recovered
    # as seven distinct clusters by the application's detection algorithm.
    all_observations = [vars(o) for event in result.values() for o in event["observations"]]
    clusters = cluster_observations(all_observations)
    if sorted(cluster["observation_count"] for cluster in clusters) != sorted(e["observation_count"] for e in result.values()):
        raise RuntimeError("Synthetic scenarios no longer match thermal event clustering")
    return result


def _event(event_id: int) -> dict:
    event = _events().get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return event


def _risk(event: dict) -> dict:
    risk = event["risk"]
    classification = event["classification"]
    return {
        "event_id": event["id"], "score": risk["score"], "severity": risk["severity"],
        "contributing_factors": risk["factors"], "explanation": risk["explanation"],
        "escalation_probability": risk.get("escalation_probability"),
        "persistence_prediction": risk.get("persistence_prediction"),
        "classification": {
            "type": classification["classification"], "confidence": classification["confidence"],
            "probabilities": classification["probabilities"], "reasoning": classification["reasoning"],
            "is_ml": classification["is_ml"], "model_status": classification["model_status"],
            "methodology": classification["methodology"],
            "features": classification["features"],
            "feature_importance": classification.get("feature_importance"),
            "top_contributing_features": classification.get("top_contributing_features", []),
            "model_version": classification.get("model_version"),
            "anomaly_score": classification.get("anomaly_score"),
            "label_provenance": classification.get("label_provenance"),
            "data_mode": _mode(),
        },
        "is_computed": True, "methodology": "Prototype operational priority from observed event features",
        "data_mode": _mode(),
    }


@router.get("/map/hotspots", response_model=MapHotspotsResponse, tags=["map"])
def demo_hotspots(risk_severity: str | None = None, limit: int = Query(100, ge=1, le=1000)):
    markers = []
    for event in _events().values():
        risk = event["risk"]
        severity = "high" if risk["severity"] in ("HIGH", "CRITICAL") else risk["severity"].lower()
        if risk_severity and risk_severity.lower() != severity:
            continue
        markers.append({
            "event_id": event["id"], "latitude": event["latitude"], "longitude": event["longitude"],
            "status": event["status"], "observation_count": event["observation_count"],
            "persistence_score": event["persistence_score"], "trend": event["persistence"]["trend"],
            "risk_score": risk["score"], "risk_severity": severity,
            "last_detection": event["end_time"],
        })
    markers = markers[:limit]
    return {"total": len(markers), "risk_summary": dict(Counter({"high": 0, "medium": 0, "low": 0}) + Counter(
        "high" if m["risk_severity"] == "high" else m["risk_severity"] for m in markers
    )), "markers": markers}


@router.get("/map/facilities/nearby", tags=["map"])
def demo_nearby_facilities(event_id: int = Query(...), radius_km: float = Query(5, ge=0.1, le=100)):
    _event(event_id)
    return {"event_id": event_id, "facilities": [], "data_mode": _mode(),
            "note": "No verified nearby facility records are available in this local mode."}


@router.get("/thermal-events", response_model=ThermalEventList, tags=["events"])
def demo_events(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), status: str | None = None):
    events = [e for e in _events().values() if status is None or e["status"] == status.upper()]
    items = events[(page - 1) * page_size:page * page_size]
    return {"total": len(events), "page": page, "page_size": page_size,
            "items": [{**{key: e[key] for key in (
                "id", "latitude", "longitude", "start_time", "end_time", "observation_count",
                "persistence_score", "status")},
                "average_intensity": e["persistence"]["average_intensity"],
                "classification_type": e["classification"]["classification"],
                "classification_model_status": e["classification"]["model_status"],
                "anomaly_score": e["classification"].get("anomaly_score"),
                "risk_score": e["risk"]["score"],
                "risk_severity": e["risk"]["severity"],
                "confidence_category": next((getattr(o, "confidence_category", None) for o in e["observations"] if getattr(o, "confidence_category", None)), None),
                "active_days": e["persistence"]["active_days"],
                "duration_hours": e["classification"]["features"].get("duration_hours"),
                "mean_frp": e["classification"]["features"].get("mean_frp"),
                "max_frp": e["classification"]["features"].get("max_frp"),
                "average_confidence": (round(sum(values) / len(values), 1) if (values := [o.confidence for o in e["observations"] if o.confidence is not None]) else None),
                "source": _source(), "location_name": e["place"]} for e in items]}


@router.get("/thermal-events/admin/non-indian", tags=["admin"])
def demo_non_indian_events():
    return {"count": 0, "events": [], "data_mode": _mode()}


@router.delete("/thermal-events/admin/non-indian", tags=["admin"])
def demo_remove_non_indian_events():
    raise HTTPException(status_code=409, detail="Local data mode is read-only.")


@router.get("/thermal-events/{event_id}", response_model=ThermalEventDetail, tags=["events"])
def demo_event_detail(event_id: int):
    event = _event(event_id)
    return {**event, "location_name": event["place"],
            "observations": [vars(o) for o in event["observations"]],
            "profile": {"baseline_status": "INSUFFICIENT_HISTORY", "data_mode": _mode()},
            "risk": _risk(event),
            "anomaly_score": event["classification"].get("anomaly_score"),
            "risk_score": event["risk"]["score"],
            "risk_severity": event["risk"]["severity"],
            "mean_frp": event["classification"]["features"].get("mean_frp"),
            "max_frp": event["classification"]["features"].get("max_frp"),
            "active_days": event["persistence"]["active_days"],
            "duration_hours": event["classification"]["features"].get("duration_hours"),
            "confidence_category": next((getattr(o, "confidence_category", None) for o in event["observations"] if getattr(o, "confidence_category", None)), None),
    }


@router.get("/thermal-events/{event_id}/history", tags=["events"])
def demo_event_history(event_id: int):
    grouped = defaultdict(list)
    for obs in _event(event_id)["observations"]:
        grouped[obs.timestamp.date()].append(obs)
    return [{"timestamp": day_obs[0].timestamp,
             "intensity": (round(sum(values) / len(values), 2) if (values := [o.intensity for o in day_obs if o.intensity is not None]) else None),
             "confidence": (round(sum(values) / len(values), 2) if (values := [o.confidence for o in day_obs if o.confidence is not None]) else None),
             "observation_count": len(day_obs)} for _, day_obs in sorted(grouped.items())]


@router.get("/thermal-events/{event_id}/risk", tags=["events"])
def demo_event_risk(event_id: int):
    return _risk(_event(event_id))


@router.get("/thermal-events/{event_id}/classification", tags=["events"])
def demo_event_classification(event_id: int):
    return _risk(_event(event_id))["classification"]


@router.get("/thermal-events/{event_id}/thermal-dna", tags=["events"])
def demo_thermal_dna(event_id: int):
    event = _event(event_id)
    return {"event_id": event_id, "thermal_dna": event["persistence"],
            "baseline": None, "baseline_status": "INSUFFICIENT_HISTORY", "data_mode": _mode()}


@router.get("/thermal-events/{event_id}/evidence", tags=["events"])
def demo_evidence(event_id: int):
    event = _event(event_id)
    from app.evidence import evidence_package, verify_evidence

    package = evidence_package(event)
    return {"event_id": event_id, "classification": _risk(event)["classification"],
            "evidence_chain": [f"{event['observation_count']} {_source()} detections",
                               f"Trend: {event['persistence']['trend']}",
                               f"Average intensity: {event['persistence']['average_intensity']} K"],
            "risk": _risk(event), "observations": [vars(o) for o in event["observations"]],
            "data_mode": _mode(), "evidence": package,
            "integrity": verify_evidence(package)}


@router.get("/evidence/{event_id}", tags=["evidence"])
def local_evidence_package(event_id: int):
    from app.evidence import evidence_package, verify_evidence

    package = evidence_package(_event(event_id))
    return {**package, "integrity": verify_evidence(package)}


@router.get("/evidence/{event_id}/verify", tags=["evidence"])
def local_verify_evidence(event_id: int):
    from app.evidence import evidence_package, verify_evidence

    return verify_evidence(evidence_package(_event(event_id)))


@router.post("/evidence/{event_id}/anchor-local", tags=["evidence"])
def local_anchor_evidence(event_id: int):
    from app.evidence import anchor_local, evidence_package

    try:
        return anchor_local(evidence_package(_event(event_id)))
    except ValueError:
        raise HTTPException(status_code=409, detail="Local evidence chain failed verification")


@router.get("/blockchain/status", tags=["evidence"])
def local_blockchain_status():
    from app.evidence import verify_chain

    return {"configured": False, "on_chain": False, "provider": None,
            "status": "NOT_CONFIGURED", "local_chain": verify_chain()}


def _filtered_observations(start_date: datetime | None, end_date: datetime | None):
    def utc(value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    return [o for e in _events().values() for o in e["observations"]
            if (start_date is None or o.timestamp >= utc(start_date))
            and (end_date is None or o.timestamp < utc(end_date))]


@router.get("/history/statistics", tags=["historical intelligence"])
def demo_statistics(start_date: datetime | None = None, end_date: datetime | None = None):
    observations = _filtered_observations(start_date, end_date)
    daily = Counter(o.timestamp.date().isoformat() for o in observations)
    events = [e for e in _events().values() if any(o in observations for o in e["observations"])]
    return {"data_mode": _mode(), "status": _local_status(), "observation_count": len(observations),
            "total_observations": len(observations), "total_events": len(events),
            "observations_by_day": dict(sorted(daily.items())),
            "observations_by_source": dict(Counter(o.source for o in observations)),
            "average_intensity_by_day": {day: (round(sum(values) / len(values), 2) if (values := [o.intensity for o in observations if o.timestamp.date().isoformat() == day and o.intensity is not None]) else None) for day in daily},
            "active_locations": sum(e["status"] != "RESOLVED" for e in events),
            "persistent_sources": sum(e["status"] == "PERSISTENT" for e in events)}


@router.get("/history/data-quality", tags=["historical intelligence"])
def demo_quality(start_date: datetime | None = None, end_date: datetime | None = None):
    observations = _filtered_observations(start_date, end_date)
    daily = Counter(o.timestamp.date().isoformat() for o in observations)
    report = {}
    capture_time = None
    if _snapshot_mode():
        from app.snapshot import snapshot_state
        state = snapshot_state()
        report, capture_time = state["validation"], state["capture_time"]
    return {"data_mode": _mode(), "status": _local_status(), "total_observations": len(observations),
            "observations_by_date": dict(sorted(daily.items())),
            "observations_by_source": dict(Counter(o.source for o in observations)),
            "observations_by_region": {}, "duplicate_count": report.get("duplicates_removed", 0),
            "invalid_coordinates": report.get("invalid_coordinates", 0),
            "confidence_distribution": dict(Counter("high" if o.confidence >= 80 else "medium" if o.confidence >= 50 else "low" for o in observations if o.confidence is not None)),
            "events_by_date": dict(Counter(e["start_time"].date().isoformat() for e in _events().values())),
            "orphan_events": 0, "observation_count_mismatches": 0,
            "recurring_locations": sum(e["persistence"]["active_days"] > 1 for e in _events().values()),
            "records_received": report.get("records_received", len(observations)),
            "records_accepted": report.get("records_accepted", len(observations)),
            "records_rejected": report.get("records_rejected", 0),
            "invalid_timestamps": report.get("invalid_timestamps", 0),
            "invalid_brightness": report.get("invalid_brightness", 0),
            "invalid_frp": report.get("invalid_frp", 0),
            "missing_values": report.get("missing_values", {}),
            "rejection_reasons": report.get("rejection_reasons", {}),
            "capture_time": capture_time,
            "database_status": "NOT_PERSISTED" if _snapshot_mode() else "NOT_USED"}


def _nearby(lat: float, lon: float, radius_km: float):
    return [o for e in _events().values() for o in e["observations"]
            if ((o.latitude - lat) * 111.0) ** 2 + ((o.longitude - lon) * 111.0 * cos(radians(lat))) ** 2 <= radius_km ** 2]


@router.get("/history/location/{lat}/{lon}/statistics", tags=["historical intelligence"])
def demo_location_statistics(lat: float = Path(..., ge=-90, le=90), lon: float = Path(..., ge=-180, le=180),
                             radius_km: float = Query(50, ge=1, le=500)):
    observations = _nearby(lat, lon, radius_km)
    intensities = [o.intensity for o in observations if o.intensity is not None]
    return {"data_mode": _mode(), "observation_count": len(observations),
            "status": _local_status() if observations else "NO_HISTORY",
            "average_intensity": round(sum(intensities) / len(intensities), 2) if intensities else None,
            "max_intensity": max(intensities) if intensities else None,
            "min_intensity": min(intensities) if intensities else None,
            "active_days": len({o.timestamp.date() for o in observations}),
            "source_distribution": dict(Counter(o.source for o in observations)),
            "baseline_status": "INSUFFICIENT_HISTORY"}


@router.get("/history/location/{lat}/{lon}/baseline", tags=["historical intelligence"])
def demo_baseline(lat: float = Path(..., ge=-90, le=90), lon: float = Path(..., ge=-180, le=180),
                  radius_km: float = Query(50, ge=1, le=500)):
    return {"status": "INSUFFICIENT_HISTORY", "baseline": None,
            "observation_count": len(_nearby(lat, lon, radius_km)),
            "note": "A short FIRMS capture cannot establish a validated historical baseline." if _snapshot_mode() else
            "Synthetic demo observations cannot establish a validated historical baseline.",
            "data_mode": _mode()}


@router.post("/history/location/{lat}/{lon}/compare", tags=["historical intelligence"])
def demo_compare(lat: float = Path(..., ge=-90, le=90), lon: float = Path(..., ge=-180, le=180),
                 radius_km: float = Query(50, ge=1, le=500)):
    return {"status": "INSUFFICIENT_HISTORY", "is_ml": False, "deviations": None,
            "baseline_status": "INSUFFICIENT_HISTORY", "data_mode": _mode()}


@router.get("/history/event/{event_id}/profile", tags=["historical intelligence"])
def demo_profile(event_id: int):
    event = _event(event_id)
    profile = compute_thermal_profile(event_id, event["observations"], None)
    profile.update({"baseline": None, "baseline_status": "INSUFFICIENT_HISTORY",
                    "status": _local_status(), "data_mode": _mode()})
    return profile


@router.post("/history/event/{event_id}/profile", tags=["historical intelligence"])
def demo_compute_profile(event_id: int):
    _event(event_id)
    raise HTTPException(status_code=409, detail="Local data mode is read-only. The GET profile endpoint computes the profile without database persistence.")


@router.post("/ingestion/firms/run", response_model=IngestionResult, tags=["ingestion"])
def demo_ingestion(request: IngestionRunRequest | None = None):
    if not _snapshot_mode():
        raise HTTPException(status_code=409, detail="Demo mode is read-only. Enable a real FIRMS snapshot or the PostGIS ingestion path.")
    if not settings.FIRMS_MAP_KEY or settings.FIRMS_MAP_KEY.startswith("YOUR_"):
        raise HTTPException(status_code=503, detail="NASA FIRMS map key is not configured.")
    from app.ingestion.capture import capture_firms_to_files
    from app.snapshot import clear_snapshot_cache, snapshot_state

    started = datetime.now(timezone.utc)
    source = request.satellite if request and request.satellite else settings.FIRMS_SATELLITE
    area = request.area if request and request.area else settings.FIRMS_AREA
    days = request.days if request and request.days else settings.FIRMS_DAYS
    try:
        report, captured = capture_firms_to_files(
            source=source, area=area, days=days, path=FilePath(settings.FIRMS_SNAPSHOT_PATH))
    except Exception:
        # The HTTP exception may contain the path-style API key URL.
        raise HTTPException(status_code=502, detail="FIRMS fetch or validation failed; existing capture retained.")
    clear_snapshot_cache()
    _events.cache_clear()
    events = snapshot_state()["events"]
    return IngestionResult(
        status="success", observations_fetched=report.records_received,
        observations_stored=report.records_accepted,
        observations_failed=report.records_rejected,
        events_created=len(events), events_updated=0,
        persistent_sources=sum(event["status"] == "PERSISTENT" for event in events.values()),
        observations_invalid_coordinates=report.invalid_coordinates,
        observations_missing_critical_fields=report.rejection_reasons.get("MISSING_COORDINATES", 0),
        observations_duplicate=report.duplicates_removed,
        started_at=started, completed_at=captured,
        storage_backend="LOCAL_FIRMS_FILES", records_accepted=report.records_accepted,
        records_rejected=report.records_rejected,
    )


@router.get("/ingestion/status", tags=["ingestion"])
def local_ingestion_status():
    if not _snapshot_mode():
        return {"data_mode": "DEMO DATA", "status": "SYNTHETIC", "database_persisted": False}
    from app.snapshot import snapshot_state
    state = snapshot_state()
    return {"data_mode": _mode(), "status": "CAPTURED", "source": state["source"],
            "area": state["area"], "captured_at": state["capture_time"],
            "database_persisted": False, **state["validation"]}

"""Thermal events API endpoints.

GET /thermal-events
GET /thermal-events/{id}
GET /thermal-events/{id}/history
GET /thermal-events/{id}/thermal-dna
GET /thermal-events/{id}/evidence
GET /thermal-events/{id}/risk
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import ThermalEvent, ThermalObservation, ThermalProfile, Prediction, RiskAssessment
from app.processing.persistence import compute_persistence_score
from app.processing.risk import classify_event, compute_risk_score, identify_non_indian_events, delete_non_indian_events
from app.ml.classifier import classify_with_fallback
from app.schemas.event import (
    ThermalEventDetail,
    ThermalEventList,
    EventHistoryPoint,
    PersistenceMetrics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/thermal-events", tags=["events"])


def _observation_dicts(observations: list[ThermalObservation]) -> list[dict]:
    return [{"id": o.id, "latitude": o.latitude, "longitude": o.longitude,
             "timestamp": o.timestamp, "intensity": o.intensity,
             "confidence": o.confidence, "metadata_json": o.metadata_json}
            for o in observations]


def _classification_payload(classification: dict) -> dict:
    return {"type": classification["classification"],
            "confidence": classification["confidence"],
            "probabilities": classification["probabilities"],
            "reasoning": classification["reasoning"],
            "is_ml": classification["is_ml"],
            "model_status": classification["model_status"],
            "methodology": classification["methodology"],
            "features": classification["features"],
            "feature_importance": classification.get("feature_importance"),
            "top_contributing_features": classification.get("top_contributing_features", []),
            "model_version": classification.get("model_version"),
            "data_mode": classification.get("data_mode", "LIVE MODE")}


@router.get("", response_model=ThermalEventList)
async def list_thermal_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, PERSISTENT, RESOLVED, UNKNOWN"),
    db: Session = Depends(get_db),
) -> ThermalEventList:
    """List all detected thermal events with pagination and optional filtering."""
    query = db.query(ThermalEvent)

    if status:
        query = query.filter(ThermalEvent.status == status)

    # Always filter to India geographic bounds (safety net for legacy data)
    query = query.filter(
        ThermalEvent.latitude >= 6.5,
        ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0,
        ThermalEvent.longitude <= 97.5,
    )

    total = query.count()
    events = query.offset((page - 1) * page_size).limit(page_size).all()

    # Aggregate once for the page, avoiding one observation query per event.
    event_ids = [e.id for e in events]
    if event_ids:
        event_obs = {
            row[0]: {"count": row[1], "intensity": row[2], "confidence": row[3],
                     "source": row[4] if row[5] == 1 else "MULTIPLE"}
            for row in db.query(
                ThermalObservation.event_id,
                func.count(ThermalObservation.id),
                func.avg(ThermalObservation.intensity),
                func.avg(ThermalObservation.confidence),
                func.min(ThermalObservation.source),
                func.count(func.distinct(ThermalObservation.source)),
            ).filter(
                ThermalObservation.event_id.in_(event_ids)
            ).group_by(ThermalObservation.event_id).all()
        }
    else:
        event_obs = {}

    return ThermalEventList(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            {
                "id": e.id,
                "latitude": e.latitude,
                "longitude": e.longitude,
                "start_time": e.start_time,
                "end_time": e.end_time,
                "observation_count": event_obs.get(e.id, {}).get("count", 0),
                "average_intensity": event_obs.get(e.id, {}).get("intensity"),
                "average_confidence": event_obs.get(e.id, {}).get("confidence"),
                "source": event_obs.get(e.id, {}).get("source"),
                "persistence_score": e.persistence_score,
                "status": e.status,
            }
            for e in events
        ],
    )


@router.get("/{event_id}", response_model=ThermalEventDetail)
async def get_thermal_event(
    event_id: int,
    db: Session = Depends(get_db),
) -> ThermalEventDetail:
    """Get a single thermal event with full detail including observations and analysis."""
    event = db.query(ThermalEvent).filter(
        ThermalEvent.id == event_id,
        # India geographic bounds — reject events outside India
        ThermalEvent.latitude >= 6.5,
        ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0,
        ThermalEvent.longitude <= 97.5,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Get observations for this event
    observations = db.query(ThermalObservation).filter(
        ThermalObservation.event_id == event_id
    ).all()

    # Use actual observation count from DB (may differ from stale stored value)
    actual_count = len(observations)

    obs_summaries = [
        {
            "id": o.id,
            "timestamp": o.timestamp,
            "latitude": o.latitude,
            "longitude": o.longitude,
            "intensity": o.intensity,
            "confidence": o.confidence,
            "source": o.source,
        }
        for o in observations
    ]

    # Compute persistence metrics
    persistence = compute_persistence_score(observations)
    obs_dicts = _observation_dicts(observations)
    classification = classify_with_fallback(obs_dicts, persistence)

    # Get profile (Thermal DNA) if available
    profile = None
    if event.profile:
        profile = {
            "frequency": event.profile.frequency,
            "average_intensity": event.profile.average_intensity,
            "duration_hours": event.profile.duration_hours,
            "spatial_stability": event.profile.spatial_stability,
            "temporal_pattern": event.profile.temporal_pattern,
            "trend": event.profile.trend,
            "baseline": event.profile.baseline,
        }

    # Get risk assessment if available, otherwise compute on-the-fly
    risk = None
    if event.risk:
        risk = {
            "score": event.risk.score,
            "severity": event.risk.severity,
            "contributing_factors": event.risk.contributing_factors,
            "explanation": event.risk.explanation,
            "is_computed": False,
            "methodology": "Rule-based heuristic assessment",
            "classification": _classification_payload(classification),
        }
    else:
        # Compute risk on-the-fly from available data
        computed_risk = compute_risk_score(persistence, classify_event(persistence, obs_dicts), obs_dicts)
        risk = {
            "score": computed_risk["score"],
            "severity": computed_risk["severity"],
            "contributing_factors": computed_risk["factors"],
            "explanation": computed_risk["explanation"],
            "is_computed": True,
            "methodology": "Rule-based heuristic assessment (computed on-the-fly)",
            "escalation_probability": computed_risk.get("escalation_probability"),
            "persistence_prediction": computed_risk.get("persistence_prediction"),
            "classification": _classification_payload(classification),
        }

    return ThermalEventDetail(
        id=event.id,
        latitude=event.latitude,
        longitude=event.longitude,
        start_time=event.start_time,
        end_time=event.end_time,
        observation_count=actual_count,
        persistence_score=event.persistence_score,
        status=event.status,
        observations=obs_summaries,
        persistence=persistence,
        profile=profile or {},
        risk=risk or {},
    )


@router.get("/{event_id}/history", response_model=list[EventHistoryPoint])
async def get_event_history(
    event_id: int,
    db: Session = Depends(get_db),
) -> list[EventHistoryPoint]:
    """Get the historical timeline of a thermal event.

    Returns a list of points showing how the event's activity changed over time.
    """
    event = db.query(ThermalEvent).filter(
        ThermalEvent.id == event_id,
        ThermalEvent.latitude >= 6.5,
        ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0,
        ThermalEvent.longitude <= 97.5,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    observations = db.query(ThermalObservation).filter(
        ThermalObservation.event_id == event_id
    ).order_by(ThermalObservation.timestamp).all()

    # Group observations by day to build a timeline
    from collections import defaultdict
    day_groups: dict = defaultdict(list)
    for obs in observations:
        day_groups[obs.timestamp.date()].append(obs)

    history = []
    for day, day_obs in sorted(day_groups.items()):
        history.append(
            EventHistoryPoint(
                timestamp=day_obs[0].timestamp,
                intensity=day_obs[0].intensity,
                confidence=day_obs[0].confidence,
                observation_count=len(day_obs),
            )
        )

    return history


@router.get("/{event_id}/thermal-dna", response_model=dict)
async def get_thermal_dna(
    event_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get the Thermal DNA profile for an event."""
    event = db.query(ThermalEvent).filter(
        ThermalEvent.id == event_id,
        ThermalEvent.latitude >= 6.5,
        ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0,
        ThermalEvent.longitude <= 97.5,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    observations = db.query(ThermalObservation).filter(
        ThermalObservation.event_id == event_id
    ).all()

    persistence = compute_persistence_score(observations)

    return {
        "event_id": event_id,
        "thermal_dna": {
            "persistence": persistence.get("trend", "UNKNOWN"),
            "frequency": f"{persistence.get('persistence_score', 0):.1f} detections/day",
            "intensity": persistence.get("average_intensity"),
            "spatial_stability": persistence.get("spatial_stability"),
            "trend": persistence.get("trend", "UNKNOWN"),
            "total_detections": persistence.get("total_detections", 0),
            "active_days": persistence.get("active_days", 0),
        },
        "baseline": persistence,
    }


@router.get("/{event_id}/evidence", response_model=dict)
async def get_event_evidence(
    event_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get the explainable evidence chain for an event."""
    event = db.query(ThermalEvent).filter(
        ThermalEvent.id == event_id,
        ThermalEvent.latitude >= 6.5,
        ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0,
        ThermalEvent.longitude <= 97.5,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    observations = db.query(ThermalObservation).filter(
        ThermalObservation.event_id == event_id
    ).all()

    persistence = compute_persistence_score(observations)

    # Compute rule-based classification and risk for the evidence chain
    obs_dicts = [
        {
            "id": o.id,
            "latitude": o.latitude,
            "longitude": o.longitude,
            "timestamp": o.timestamp,
            "intensity": o.intensity,
            "confidence": o.confidence,
        }
        for o in observations
    ]
    classification = classify_with_fallback(obs_dicts, persistence)
    computed_risk = compute_risk_score(persistence, classify_event(persistence, obs_dicts), obs_dicts)

    evidence_items = [
        f"✓ {persistence.get('total_detections', 0)} detections over {persistence.get('active_days', 0)} day(s)",
        f"✓ Thermal intensity: {persistence.get('average_intensity', 'N/A')} K",
        f"✓ Trend: {persistence.get('trend', 'UNKNOWN')}",
        f"✓ Spatial stability: {persistence.get('spatial_stability', 'N/A')}",
        f"✓ Event status: {event.status}",
    ]

    return {
        "event_id": event_id,
        "classification": _classification_payload(classification),
        "evidence_chain": evidence_items,
        "risk": {
            "score": computed_risk["score"],
            "severity": computed_risk["severity"],
            "methodology": "Rule-based heuristic assessment",
        },
        "observations": [
            {
                "timestamp": o.timestamp,
                "latitude": o.latitude,
                "longitude": o.longitude,
                "intensity": o.intensity,
                "confidence": o.confidence,
            }
            for o in observations
        ],
    }


@router.get("/{event_id}/risk", response_model=dict)
async def get_event_risk(
    event_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Get the risk assessment for an event.

    If no stored risk assessment exists, computes one on-the-fly from available data.
    """
    event = db.query(ThermalEvent).filter(
        ThermalEvent.id == event_id,
        ThermalEvent.latitude >= 6.5,
        ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0,
        ThermalEvent.longitude <= 97.5,
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    observations = db.query(ThermalObservation).filter(
        ThermalObservation.event_id == event_id
    ).all()
    persistence = compute_persistence_score(observations)
    obs_dicts = _observation_dicts(observations)
    classification = classify_with_fallback(obs_dicts, persistence)

    if event.risk:
        return {
            "event_id": event_id,
            "score": event.risk.score,
            "severity": event.risk.severity,
            "contributing_factors": event.risk.contributing_factors,
            "explanation": event.risk.explanation,
            "created_at": event.risk.created_at,
            "is_computed": False,
            "methodology": "Rule-based heuristic assessment",
            "classification": _classification_payload(classification),
        }

    # Compute on-the-fly
    computed_risk = compute_risk_score(persistence, classify_event(persistence, obs_dicts), obs_dicts)

    return {
        "event_id": event_id,
        "score": computed_risk["score"],
        "severity": computed_risk["severity"],
        "contributing_factors": computed_risk["factors"],
        "explanation": computed_risk["explanation"],
        "escalation_probability": computed_risk.get("escalation_probability"),
        "persistence_prediction": computed_risk.get("persistence_prediction"),
        "classification": _classification_payload(classification),
        "is_computed": True,
        "methodology": "Rule-based heuristic assessment (computed on-the-fly)",
    }


@router.get("/{event_id}/classification", response_model=dict)
async def get_event_classification(event_id: int, db: Session = Depends(get_db)) -> dict:
    """Classify an event with a trained local model or the documented rule fallback."""
    event = db.query(ThermalEvent).filter(
        ThermalEvent.id == event_id,
        ThermalEvent.latitude >= 6.5, ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0, ThermalEvent.longitude <= 97.5,
    ).first()
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    observations = db.query(ThermalObservation).filter(ThermalObservation.event_id == event_id).all()
    persistence = compute_persistence_score(observations)
    return _classification_payload(classify_with_fallback(_observation_dicts(observations), persistence))


# ---------------------------------------------------------------------------
# Data management endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/non-indian", tags=["admin"])
async def list_non_indian_events(
    db: Session = Depends(get_db),
) -> dict:
    """List all thermal events currently outside India boundaries.

    These events should not appear in the India dashboard but may exist
    from legacy ingestion runs before the India filter was added.
    """
    non_indian = identify_non_indian_events(db)
    return {
        "count": len(non_indian),
        "events": non_indian,
    }


@router.delete("/admin/non-indian", tags=["admin"])
async def remove_non_indian_events(
    db: Session = Depends(get_db),
) -> dict:
    """Delete all thermal events outside India boundaries.

    This removes non-Indian events and their associated observations
    from the database. Use with caution.
    """
    result = delete_non_indian_events(db)
    return {
        "status": "deleted",
        "deleted_count": result["deleted"],
    }

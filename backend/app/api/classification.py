"""Inference for the optional real-FIRMS weakly supervised classifier."""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import ThermalEvent, ThermalObservation
from app.ml.classifier import classify_with_fallback
from app.ml.weak_classifier import predict_weak
from app.processing.persistence import compute_persistence_score

router = APIRouter(tags=["classification"])


class ClassificationRequest(BaseModel):
    event_id: int = Field(..., ge=1)


def _infer(event_id: int, db: Session) -> dict:
    if settings.DEMO_MODE:
        raise HTTPException(status_code=409, detail="Real FIRMS classification is unavailable in synthetic demo mode")
    if settings.FIRMS_SNAPSHOT_PATH:
        from app.snapshot import snapshot_state
        state = snapshot_state()
        event = state["events"].get(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Thermal event not found")
        path = Path(settings.FIRMS_SNAPSHOT_PATH)
        capture_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        observations = event["observations"]
        anomaly_score = event["classification"].get("anomaly_score")
    else:
        event = db.get(ThermalEvent, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Thermal event not found")
        observations = db.query(ThermalObservation).filter(
            ThermalObservation.event_id == event_id,
        ).order_by(ThermalObservation.timestamp).all()
        if not observations:
            raise HTTPException(status_code=422, detail="Event has no observations")
        persistence = compute_persistence_score(observations)
        anomaly_score = classify_with_fallback(observations, persistence).get("anomaly_score")
        capture_hash = None
    try:
        return predict_weak(event_id, observations, anomaly_score=anomaly_score,
                            capture_hash=capture_hash)
    except LookupError:
        raise HTTPException(status_code=503, detail="Compatible real-FIRMS classifier artifact unavailable") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/classification")
def classify_event_request(request: ClassificationRequest, db: Session = Depends(get_db)) -> dict:
    return _infer(request.event_id, db)


@router.get("/thermal-events/{event_id}/weak-classification")
def classify_event_by_id(event_id: int, db: Session = Depends(get_db)) -> dict:
    return _infer(event_id, db)

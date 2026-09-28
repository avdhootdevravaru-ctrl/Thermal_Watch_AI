"""Dynamic PDF reports for thermal events."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import ThermalEvent, ThermalObservation
from app.evidence import evidence_package, verify_evidence
from app.geo.india import INDIA_BOUNDARY_SOURCE, india_sql_contains
from app.ml.classifier import classify_with_fallback
from app.ml.weak_classifier import predict_weak
from app.processing.geo_context import resolve_location_name
from app.processing.persistence import compute_persistence_score
from app.processing.risk import classify_event, compute_risk_score
from app.reports.event_pdf import render_event_pdf


router = APIRouter(tags=["reports"])


def _database_event(event_id: int, db: Session) -> dict:
    event = db.query(ThermalEvent).filter(
        ThermalEvent.id == event_id,
        india_sql_contains(ThermalEvent.latitude, ThermalEvent.longitude),
    ).first()
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    observations = db.query(ThermalObservation).filter(ThermalObservation.event_id == event_id).all()
    persistence = compute_persistence_score(observations)
    rows = [vars(o) for o in observations]
    classification = classify_with_fallback(rows, persistence)
    risk = compute_risk_score(persistence, classify_event(persistence, rows), rows)
    return {
        "id": event.id, "place": resolve_location_name(event.latitude, event.longitude),
        "latitude": event.latitude, "longitude": event.longitude,
        "start_time": event.start_time, "end_time": event.end_time,
        "status": event.status, "observations": observations,
        "persistence": persistence, "classification": classification,
        "risk": risk, "data_mode": "LIVE MODE",
    }


@router.get("/thermal-events/{event_id}/report.pdf")
def download_event_report(event_id: int, db: Session = Depends(get_db)) -> Response:
    """Generate a PDF from the selected event's current data."""
    validation = {}
    if settings.DEMO_MODE or settings.FIRMS_SNAPSHOT_PATH:
        from app.demo import _event
        event = _event(event_id)
        if settings.FIRMS_SNAPSHOT_PATH:
            from app.snapshot import snapshot_state
            validation = snapshot_state()["validation"]
    else:
        event = _database_event(event_id, db)

    package = evidence_package(event)
    integrity = verify_evidence(package)
    weak = None
    if event["data_mode"] != "DEMO DATA":
        try:
            weak = predict_weak(event_id, event["observations"], anomaly_score=event["classification"].get("anomaly_score"))
        except (LookupError, ValueError):
            weak = None
    document = render_event_pdf({
        "event": event, "evidence": package, "integrity": integrity,
        "weak": weak, "validation": validation,
        "boundary_source": INDIA_BOUNDARY_SOURCE,
        "generated_at": datetime.now(timezone.utc),
    })
    return Response(
        content=document,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="thermal-watch-event-{event_id}.pdf"'},
    )

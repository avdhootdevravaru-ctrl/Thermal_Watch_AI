"""Persist a validated capture idempotently; never invent prediction confidence."""
import sys
import json
from pathlib import Path
from collections import Counter
from sqlalchemy import select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db.base import _get_engine
from app.db.models import ThermalObservation, ThermalEvent, ThermalProfile, RiskAssessment
from app.snapshot import snapshot_state
from app.processing.persistence import compute_persistence_score
from app.processing.risk import classify_event, compute_risk_score


def observation_key(row):
    return (row.source, row.timestamp, row.latitude, row.longitude, row.sensor)


def persist_snapshot():
    state = snapshot_state()
    added_events = added_observations = 0
    with Session(_get_engine()) as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(26162)"))
        existing = {observation_key(row): row for row in session.scalars(select(ThermalObservation))}
        for event in state["events"].values():
            members = event["observations"]
            matches = [existing[observation_key(row)] for row in members if observation_key(row) in existing]
            ids = Counter(row.event_id for row in matches if row.event_id is not None)
            if len(ids) > 1:
                raise ValueError("Capture joins multiple persisted events; explicit reconciliation is required")
            db_event = session.get(ThermalEvent, next(iter(ids))) if ids else None
            if db_event is None:
                db_event = ThermalEvent(**{key: event[key] for key in (
                    "latitude", "longitude", "start_time", "end_time", "observation_count", "persistence_score", "status")})
                session.add(db_event)
                session.flush()
                added_events += 1
            for row in members:
                key = observation_key(row)
                if key in existing:
                    existing[key].event_id = db_event.id
                    continue
                stored = ThermalObservation(event_id=db_event.id,
                    **{key: getattr(row, key) for key in ("timestamp", "latitude", "longitude", "intensity", "confidence", "source", "sensor", "metadata_json")},
                    geometry=f"SRID=4326;POINT({row.longitude} {row.latitude})")
                session.add(stored)
                existing[key] = stored
                added_observations += 1
            session.flush()
            observations = list(session.scalars(select(ThermalObservation).where(ThermalObservation.event_id == db_event.id)))
            persistence = compute_persistence_score(observations)
            db_event.observation_count = len(observations)
            db_event.start_time = min(row.timestamp for row in observations)
            db_event.end_time = max(row.timestamp for row in observations)
            db_event.latitude = sum(row.latitude for row in observations) / len(observations)
            db_event.longitude = sum(row.longitude for row in observations) / len(observations)
            db_event.persistence_score = persistence["persistence_score"]
            profile = session.get(ThermalProfile, db_event.id) or ThermalProfile(event_id=db_event.id)
            for key, value in persistence.items():
                if key in ThermalProfile.__table__.columns and key != "event_id":
                    setattr(profile, key, value)
            session.add(profile)
            obs_dicts = [{key: getattr(row, key) for key in ("timestamp", "latitude", "longitude", "intensity", "confidence", "source", "sensor", "metadata_json")} for row in observations]
            risk = compute_risk_score(persistence, classify_event(persistence, obs_dicts), obs_dicts)
            stored_risk = session.get(RiskAssessment, db_event.id) or RiskAssessment(event_id=db_event.id)
            stored_risk.score = risk["score"]
            stored_risk.severity = risk["severity"]
            stored_risk.contributing_factors = risk.get("factors", [])
            stored_risk.explanation = risk.get("explanation")
            session.add(stored_risk)
            # Legacy predictions require confidence. An anomaly score is not
            # confidence; that inference remains available through its API.
        session.flush()
        counts = {"observations": session.execute(text("SELECT count(*) FROM thermal_observations")).scalar_one(),
                  "events": session.execute(text("SELECT count(*) FROM thermal_events")).scalar_one()}
    return {"added_observations": added_observations, "added_events": added_events, "persisted": counts}


if __name__ == "__main__":
    try:
        print(json.dumps(persist_snapshot(), indent=2))
    except Exception as exc:
        print(f"Snapshot persistence failed ({type(exc).__name__}); transaction rolled back.", file=sys.stderr)
        sys.exit(1)

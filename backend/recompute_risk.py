"""Recompute all stored RiskAssessment records using the new scoring algorithm.

This script:
1. Queries all RiskAssessment records
2. For each, fetches the event's observations
3. Recomputes persistence metrics, classification, and risk score
4. Updates the stored record with new score and severity
"""
import sys
sys.path.insert(0, '/d/claude_config/backend')

from app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import ThermalEvent, ThermalObservation, RiskAssessment
from app.processing.persistence import compute_persistence_score
from app.processing.risk import classify_event, compute_risk_score
from datetime import datetime, timezone
from collections import Counter

engine = create_engine(settings.DATABASE_URL)
db = Session(engine)

# Get all events that have associated observations
events_query = db.query(ThermalEvent).join(ThermalObservation).distinct().all()
print(f"Events with observations: {len(events_query)}")

updated_count = 0
errors = 0

for event in events_query:
    try:
        observations = db.query(ThermalObservation).filter(
            ThermalObservation.event_id == event.id
        ).all()

        if not observations:
            continue

        # Compute persistence metrics
        persistence = compute_persistence_score(observations)

        # Prepare observation dicts for classification/risk scoring
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

        # Classify event
        classification = classify_event(persistence, obs_dicts)

        # Compute risk score
        risk_result = compute_risk_score(persistence, classification, obs_dicts)

        # Get or create RiskAssessment record
        risk = db.query(RiskAssessment).filter(RiskAssessment.event_id == event.id).first()

        if risk:
            risk.score = risk_result["score"]
            risk.severity = risk_result["severity"]
            risk.contributing_factors = risk_result["factors"]
            risk.explanation = risk_result["explanation"]
            risk.updated_at = datetime.now(timezone.utc)
        else:
            risk = RiskAssessment(
                event_id=event.id,
                score=risk_result["score"],
                severity=risk_result["severity"],
                contributing_factors=risk_result["factors"],
                explanation=risk_result["explanation"],
            )
            db.add(risk)

        updated_count += 1
    except Exception as e:
        print(f"Error processing event {event.id}: {e}")
        errors += 1

db.commit()

# Report new distribution
ras = db.query(RiskAssessment).all()
sevs = Counter(r.severity for r in ras)
print(f"\n--- Recomputation Complete ---")
print(f"Updated records: {updated_count}")
print(f"Errors: {errors}")
print(f"Total RiskAssessment records: {len(ras)}")
print(f"New severity distribution: {dict(sevs)}")
scores = [r.score for r in ras]
if scores:
    print(f"New score range: {min(scores):.1f} - {max(scores):.1f}")
    print(f"Average score: {sum(scores)/len(scores):.1f}")

db.close()
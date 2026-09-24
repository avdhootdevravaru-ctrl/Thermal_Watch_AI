"""Simple script to update all RiskAssessment records with current scores.

This is a quick fix to recompute and update the risk assessments
without the error from the previous script."""
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

# Get all events with observations
events = db.query(ThermalEvent).join(ThermalObservation).distinct().all()
print(f"Events with observations: {len(events)}")

# Update each event
updated = 0
errors = 0

for event in events:
    try:
        observations = db.query(ThermalObservation).filter(
            ThermalObservation.event_id == event.id
        ).all()

        if not observations:
            continue

        # Compute persistence and risk using current logic
        persistence = compute_persistence_score(observations)
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

        classification = classify_event(persistence, obs_dicts)
        risk_result = compute_risk_score(persistence, classification, obs_dicts)

        # Update the RiskAssessment record
        risk = db.query(RiskAssessment).filter(RiskAssessment.event_id == event.id).first()
        if risk:
            risk.score = risk_result["score"]
            risk.severity = risk_result["severity"]
            risk.contributing_factors = risk_result["factors"]
            risk.explanation = risk_result["explanation"]
            risk.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            risk = RiskAssessment(
                event_id=event.id,
                score=risk_result["score"],
                severity=risk_result["severity"],
                contributing_factors=risk_result["factors"],
                explanation=risk_result["explanation"],
            )
            db.add(risk)
            updated += 1
    except Exception as e:
        print(f"Error for event {event.id}: {e}")
        errors += 1

db.commit()

# Check final distribution
ras = db.query(RiskAssessment).all()
sevs = Counter(r.severity for r in ras)
print(f"\n--- Update Complete ---")
print(f"Total records: {len(ras)}")
print(f"Updated: {updated}")
print(f"Errors: {errors}")
print(f"New severity: {dict(sevs)}")

scores = [r.score for r in ras]
if scores:
    print(f"Score range: {min(scores):.1f} - {max(scores):.1f}")

    # Show distribution
    buckets = {"0-19": 0, "20-29": 0, "30-39": 0, "40-49": 0, "50-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90+": 0}
    for s in scores:
        if s < 20: buckets["0-19"] += 1
        elif s < 30: buckets["20-29"] += 1
        elif s < 40: buckets["30-39"] += 1
        elif s < 50: buckets["40-49"] += 1
        elif s < 60: buckets["50-59"] += 1
        elif s < 70: buckets["60-69"] += 1
        elif s < 80: buckets["70-79"] += 1
        elif s < 90: buckets["80-89"] += 1
        else: buckets["90+"] += 1

    print("Score distribution:")
    for bucket, count in sorted(buckets.items()):
        if count > 0:
            print(f"  {bucket}: {count} events")

db.close()
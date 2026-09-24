"""Recompute all stored RiskAssessment records using the new scoring algorithm.

This script:
1. Queries all ThermalEvent records
2. For each, fetches the associated observations
3. Recomputes persistence metrics, classification, and risk score using the new algorithm
4. Updates the stored RiskAssessment record with new values
5. Runs on the full dataset to ensure complete coverage
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

# Get all events that have observations
events_query = db.query(ThermalEvent).join(ThermalObservation).distinct().all()
print(f"Events with observations: {len(events_query)}")

updated_count = 0
errors = 0

for i, event in enumerate(events_query):
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

        # Compute risk score using new algorithm
        risk_result = compute_risk_score(persistence, classification, obs_dicts)

        # Get or create RiskAssessment record
        risk = db.query(RiskAssessment).filter(RiskAssessment.event_id == event.id).first()

        if risk:
            risk.score = risk_result["score"]
            risk.severity = risk_result["severity"]
            risk.contributing_factors = risk_result["factors"]
            risk.explanation = risk_result["explanation"]
            risk.updated_at = datetime.now(timezone.utc)
            updated_count += 1
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

        # Report progress every 100 events
        if (i + 1) % 100 == 0:
            print(f"Processed {i + 1}/{len(events_query)} events")

    except Exception as e:
        print(f"Error processing event {event.id}: {e}")
        errors += 1

db.commit()

# Verify the complete distribution
ras = db.query(RiskAssessment).all()
sevs = Counter(r.severity for r in ras)
print(f"\n--- Recomputation Complete ---")
print(f"Total RiskAssessment records: {len(ras)}")
print(f"Updated records: {updated_count}")
print(f"Errors: {errors}")
print(f"New severity distribution: {dict(sevs)}")
scores = [r.score for r in ras]
if scores:
    print(f"New score range: {min(scores):.1f} - {max(scores):.1f}")
    print(f"Average score: {sum(scores)/len(scores):.1f}")

    # Bucket distribution
    buckets = {'0-19':0, '20-29':0, '30-39':0, '40-49':0, '50-59':0, '60-69':0, '70-79':0, '80-89':0, '90-99':0}
    for s in scores:
        bucket = int(s) // 10 * 10
        if bucket <= 99:
            buckets[f"{bucket}-{bucket+9}"] += 1
    print(f"Score buckets: {dict(buckets)}")

db.close()
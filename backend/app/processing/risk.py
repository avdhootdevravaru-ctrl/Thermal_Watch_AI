"""Risk assessment and event classification module.

This module provides rule-based risk assessment and classification for thermal events.
It uses observable features from the data to generate risk scores and classifications.

Note: This is a heuristic/rule-based assessment system, not an ML model.
All outputs are derived from observable metrics and are clearly labeled as such.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

from app.db.models import RiskAssessment, ThermalEvent, ThermalObservation

logger = logging.getLogger(__name__)

# India bounding box (approximate)
INDIA_BOUNDS = {
    "min_lat": 6.5,
    "max_lat": 35.5,
    "min_lon": 68.0,
    "max_lon": 97.5,
}


def is_in_india(lat: float, lon: float) -> bool:
    """Check if a point is within India boundaries.

    Uses simple bounding box check. For more accuracy, use PostGIS with actual
    India polygon geometry.
    """
    return (
        INDIA_BOUNDS["min_lat"] <= lat <= INDIA_BOUNDS["max_lat"]
        and INDIA_BOUNDS["min_lon"] <= lon <= INDIA_BOUNDS["max_lon"]
    )


def filter_india_observations(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter observations to only those within India boundaries."""
    return [
        obs for obs in observations
        if obs.get("latitude") is not None
        and obs.get("longitude") is not None
        and is_in_india(obs["latitude"], obs["longitude"])
    ]


def classify_event(
    persistence: Dict[str, Any],
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Classify a thermal event based on observable characteristics.

    This is a rule-based classification using available features:
    - Detection frequency (detections per day)
    - Intensity (brightness temperature)
    - Trend (increasing/decreasing/stable)
    - Duration (active days)
    - Source (VIIRS vs MODIS)

    Returns:
        classification: str (INDUSTRIAL_THERMAL_SOURCE, AGRICULTURAL_BURNING,
                            PERSISTENT_THERMAL_SOURCE, OTHER, UNKNOWN)
        confidence: float (0-1, based on data quality)
        reasoning: list[str] of contributing factors
    """
    if not observations:
        return {
            "classification": "UNKNOWN",
            "confidence": 0.0,
            "reasoning": ["No observations available for classification"],
            "probabilities": {},
        }

    total_detections = len(observations)
    active_days = persistence.get("active_days", 0)
    persistence_score = persistence.get("persistence_score", 0.0)
    trend = persistence.get("trend", "UNKNOWN")
    avg_intensity = persistence.get("average_intensity")

    # Compute probabilities for each class
    probabilities = {}

    # 1. Industrial Thermal Source: high frequency, stable location, consistent intensity
    industrial_score = 0.0
    if persistence_score >= 5.0:
        industrial_score += 0.4
    if active_days >= 3:
        industrial_score += 0.3
    if trend == "STABLE":
        industrial_score += 0.2
    if avg_intensity and avg_intensity > 330:  # Higher temp suggests industrial
        industrial_score += 0.1
    probabilities["INDUSTRIAL_THERMAL_SOURCE"] = min(industrial_score, 1.0)

    # 2. Persistent Thermal Source: high detection frequency, ongoing
    persistent_score = 0.0
    if persistence_score >= 3.0:
        persistent_score += 0.3
    if active_days >= 2:
        persistent_score += 0.3
    if total_detections >= 5:
        persistent_score += 0.2
    if trend in ("STABLE", "INCREASING"):
        persistent_score += 0.2
    probabilities["PERSISTENT_THERMAL_SOURCE"] = min(persistent_score, 1.0)

    # 3. Agricultural Burning: lower frequency, seasonal pattern, moderate intensity
    agricultural_score = 0.0
    if 1.0 <= persistence_score <= 5.0:
        agricultural_score += 0.3
    if 1 <= active_days <= 7:
        agricultural_score += 0.3
    if avg_intensity and 300 <= avg_intensity <= 360:
        agricultural_score += 0.2
    if trend in ("DECREASING", "STABLE"):
        agricultural_score += 0.2
    probabilities["AGRICULTURAL_BURNING"] = min(agricultural_score, 1.0)

    # 4. Other/Unknown: single detections or unusual patterns
    other_score = 0.0
    if total_detections <= 2:
        other_score += 0.5
    if persistence_score < 1.0:
        other_score += 0.3
    if trend == "UNKNOWN":
        other_score += 0.2
    probabilities["OTHER"] = min(other_score, 1.0)

    # Normalize probabilities
    total = sum(probabilities.values())
    if total > 0:
        probabilities = {k: v / total for k, v in probabilities.items()}
    else:
        probabilities = {k: 0.25 for k in probabilities.keys()}

    # Select classification with highest probability
    classification = max(probabilities, key=probabilities.get)  # type: ignore

    # Compute confidence based on data quality
    confidence = 0.0
    if total_detections >= 10:
        confidence += 0.3
    elif total_detections >= 5:
        confidence += 0.2
    elif total_detections >= 2:
        confidence += 0.1

    if active_days >= 3:
        confidence += 0.2
    elif active_days >= 1:
        confidence += 0.1

    if avg_intensity is not None:
        confidence += 0.2

    if trend != "UNKNOWN":
        confidence += 0.2

    confidence = min(confidence, 0.9)  # Cap at 90% for rule-based

    # Generate reasoning
    reasoning = []
    if total_detections >= 10:
        reasoning.append(f"High detection count ({total_detections} observations)")
    if persistence_score >= 5.0:
        reasoning.append(f"High persistence ({persistence_score:.1f} detections/day)")
    if avg_intensity:
        reasoning.append(f"Average intensity: {avg_intensity:.0f}K")
    if trend != "UNKNOWN":
        reasoning.append(f"Temporal trend: {trend}")
    if active_days >= 3:
        reasoning.append(f"Active for {active_days} days")

    return {
        "classification": classification,
        "confidence": confidence,
        "reasoning": reasoning,
        "probabilities": probabilities,
    }


def compute_risk_score(
    persistence: Dict[str, Any],
    classification: Dict[str, Any],
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute risk assessment based on available features.

    Risk factors:
    - Observation count (more detections = higher risk)
    - Persistence score (higher = more concerning)
    - Active days (longer duration = higher risk)
    - Trend (INCREASING = escalation risk)
    - Intensity (higher = more severe)
    - Classification (industrial = higher risk than agricultural)

    Returns:
        score: float (0-100)
        severity: str (LOW, MEDIUM, HIGH, CRITICAL)
        factors: list of contributing factors with weights
        explanation: human-readable explanation
    """
    if not observations:
        return {
            "score": 0.0,
            "severity": "LOW",
            "factors": [],
            "explanation": "No data available for risk assessment",
        }

    factors: List[Dict[str, Any]] = []
    total_weight = 100.0  # All weights sum to 100

    # Factor 1: Detection frequency (weight: 25%)
    total_detections = len(observations)
    detection_weight = 25.0
    if total_detections >= 20:
        detection_score = 25.0
        factors.append({"factor": "High detection count", "score": 25.0, "weight": 25.0})
    elif total_detections >= 10:
        detection_score = 18.0
        factors.append({"factor": "Moderate detection count", "score": 18.0, "weight": 25.0})
    elif total_detections >= 5:
        detection_score = 10.0
        factors.append({"factor": "Low detection count", "score": 10.0, "weight": 25.0})
    elif total_detections >= 2:
        detection_score = 5.0
        factors.append({"factor": "Minimal detections", "score": 5.0, "weight": 25.0})
    else:
        detection_score = 1.0
        factors.append({"factor": "Single detection", "score": 1.0, "weight": 25.0})

    # Factor 2: Persistence (weight: 25%)
    persistence_score = persistence.get("persistence_score", 0.0)
    if persistence_score >= 10.0:
        persistence_factor_score = 25.0
        factors.append({"factor": f"High persistence ({persistence_score:.1f}/day)", "score": 25.0, "weight": 25.0})
    elif persistence_score >= 5.0:
        persistence_factor_score = 18.0
        factors.append({"factor": f"Moderate persistence ({persistence_score:.1f}/day)", "score": 18.0, "weight": 25.0})
    elif persistence_score >= 2.0:
        persistence_factor_score = 10.0
        factors.append({"factor": f"Low persistence ({persistence_score:.1f}/day)", "score": 10.0, "weight": 25.0})
    elif persistence_score >= 1.0:
        persistence_factor_score = 5.0
        factors.append({"factor": f"Minimal persistence ({persistence_score:.1f}/day)", "score": 5.0, "weight": 25.0})
    else:
        persistence_factor_score = 1.0
        factors.append({"factor": f"Minimal persistence ({persistence_score:.1f}/day)", "score": 1.0, "weight": 25.0})

    # Factor 3: Active days (weight: 15%)
    active_days = persistence.get("active_days", 0)
    if active_days >= 7:
        duration_score = 15.0
        factors.append({"factor": f"Long duration ({active_days} days)", "score": 15.0, "weight": 15.0})
    elif active_days >= 3:
        duration_score = 10.0
        factors.append({"factor": f"Moderate duration ({active_days} days)", "score": 10.0, "weight": 15.0})
    elif active_days >= 1:
        duration_score = 5.0
        factors.append({"factor": f"Short duration ({active_days} day)", "score": 5.0, "weight": 15.0})
    else:
        duration_score = 1.0
        factors.append({"factor": "Single day event", "score": 1.0, "weight": 15.0})

    # Factor 4: Trend/Escalation (weight: 20%)
    trend = persistence.get("trend", "UNKNOWN")
    if trend == "INCREASING":
        trend_score = 20.0
        factors.append({"factor": "Escalating trend", "score": 20.0, "weight": 20.0})
    elif trend == "STABLE":
        trend_score = 10.0
        factors.append({"factor": "Stable trend", "score": 10.0, "weight": 20.0})
    elif trend == "DECREASING":
        trend_score = 5.0
        factors.append({"factor": "Decreasing trend", "score": 5.0, "weight": 20.0})
    else:
        trend_score = 1.0  # Reduced from 5.0 to ensure scores spread better
        factors.append({"factor": "Trend unknown", "score": 1.0, "weight": 20.0})

    # Factor 5: Intensity (weight: 15%)
    avg_intensity = persistence.get("average_intensity")
    if avg_intensity:
        if avg_intensity >= 400:
            intensity_score = 15.0
            factors.append({"factor": f"Very high intensity ({avg_intensity:.0f}K)", "score": 15.0, "weight": 15.0})
        elif avg_intensity >= 350:
            intensity_score = 12.0
            factors.append({"factor": f"High intensity ({avg_intensity:.0f}K)", "score": 12.0, "weight": 15.0})
        elif avg_intensity >= 300:
            intensity_score = 8.0
            factors.append({"factor": f"Moderate intensity ({avg_intensity:.0f}K)", "score": 8.0, "weight": 15.0})
        else:
            intensity_score = 4.0
            factors.append({"factor": f"Low intensity ({avg_intensity:.0f}K)", "score": 4.0, "weight": 15.0})
    else:
        intensity_score = 1.0  # Reduced from 3.0 to ensure scores spread better
        factors.append({"factor": "Intensity unknown", "score": 1.0, "weight": 15.0})

    # Calculate total score (0-100 scale)
    raw_score = detection_score + persistence_factor_score + duration_score + trend_score + intensity_score
    # Normalize to 0-100 based on total weight (100)
    score = (raw_score / 100.0) * 100.0
    score = min(max(score, 0.0), 100.0)

    # Determine severity
    if score >= 75:
        severity = "CRITICAL"
    elif score >= 50:
        severity = "HIGH"
    elif score >= 25:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    # Generate explanation
    explanations = []
    if trend == "INCREASING":
        explanations.append("Thermal activity is increasing over time")
    if persistence_score >= 5.0:
        explanations.append("High detection frequency suggests persistent source")
    if active_days >= 3:
        explanations.append(f"Thermal source active for {active_days} days")
    if avg_intensity and avg_intensity >= 350:
        explanations.append("Very high brightness temperature indicates intense heat source")
    if classification["classification"] == "INDUSTRIAL_THERMAL_SOURCE":
        explanations.append("Thermal pattern matches the industrial-source heuristic; facility context is unverified")
    if classification["classification"] == "AGRICULTURAL_BURNING":
        explanations.append("Thermal pattern matches the agricultural-burning heuristic; land-use context is unverified")

    explanation = ". ".join(explanations) if explanations else "No specific risk factors identified."

    return {
        "score": round(score, 1),
        "severity": severity,
        "factors": factors,
        "explanation": explanation,
        # No validated forecasting model exists. Keep these legacy response
        # keys explicit rather than emitting invented probabilities/horizons.
        "escalation_probability": None,
        "persistence_prediction": None,
        "forecast_status": "UNAVAILABLE_NO_VALIDATED_MODEL",
    }


def generate_risk_assessment(
    event_id: int,
    persistence: Dict[str, Any],
    observations: List[Dict[str, Any]],
    db: Any,
) -> RiskAssessment:
    """Generate and store a complete risk assessment for an event.

    This function:
    1. Classifies the event type based on observable features
    2. Computes risk score and severity
    3. Stores the assessment in the database
    """
    # Classify the event
    classification = classify_event(persistence, observations)

    # Compute risk score
    risk = compute_risk_score(persistence, classification, observations)

    # Create risk assessment
    risk_assessment = RiskAssessment(
        event_id=event_id,
        score=risk["score"],
        severity=risk["severity"],
        contributing_factors=risk["factors"],
        explanation=risk["explanation"],
    )

    db.add(risk_assessment)
    db.commit()
    db.refresh(risk_assessment)

    logger.info(
        "Generated risk assessment for event %d: score=%.1f severity=%s classification=%s",
        event_id,
        risk["score"],
        risk["severity"],
        classification["classification"],
    )

    return risk_assessment


def identify_non_indian_events(db: Any) -> List[Dict[str, Any]]:
    """Identify thermal events outside India boundaries.

    Returns a list of event dicts with id, latitude, longitude, observation_count
    for events that fall outside the India bounding box.

    These events were likely ingested before the India filter was applied or
    from a misconfigured ingestion run.
    """
    from app.db.models import ThermalEvent, ThermalObservation

    # Find events outside India bounding box
    non_indian = db.query(ThermalEvent).filter(
        (ThermalEvent.latitude < 6.5) |
        (ThermalEvent.latitude > 35.5) |
        (ThermalEvent.longitude < 68.0) |
        (ThermalEvent.longitude > 97.5)
    ).all()

    result = []
    for event in non_indian:
        obs_count = db.query(ThermalObservation).filter(
            ThermalObservation.event_id == event.id
        ).count()
        result.append({
            "id": event.id,
            "latitude": event.latitude,
            "longitude": event.longitude,
            "status": event.status,
            "observation_count": obs_count,
            "start_time": event.start_time.isoformat() if event.start_time else None,
        })

    return result


def delete_non_indian_events(db: Any) -> Dict[str, int]:
    """Delete all thermal events outside India boundaries.

    Also cascades to delete associated observations (via FK ondelete=CASCADE).

    Returns a dict with count of deleted events.
    """
    from app.db.models import ThermalEvent

    deleted = db.query(ThermalEvent).filter(
        (ThermalEvent.latitude < 6.5) |
        (ThermalEvent.latitude > 35.5) |
        (ThermalEvent.longitude < 68.0) |
        (ThermalEvent.longitude > 97.5)
    ).delete(synchronize_session=False)
    db.commit()

    return {"deleted": deleted}

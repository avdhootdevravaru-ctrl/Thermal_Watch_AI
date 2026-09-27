"""Event feature extraction and explicitly labelled prototype classification."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from math import cos, radians, sqrt
from pathlib import Path
from statistics import mean, pvariance
from typing import Any, Iterable

import joblib
import numpy as np

from app.config import settings
from app.processing.persistence import compute_persistence_score
from app.processing.risk import classify_event

logger = logging.getLogger(__name__)

FEATURE_NAMES = (
    "observation_count", "active_days", "persistence_score", "duration_hours",
    "temporal_trend", "spatial_stability",
    "mean_intensity", "max_intensity", "intensity_variance",
    "mean_confidence", "mean_frp", "max_frp", "frp_variance",
    "mean_secondary_brightness", "mean_scan", "mean_track", "night_fraction",
    "spatial_spread_km", "recurrence_days", "historical_activity",
    "facility_distance_km",
)
FEATURE_VERSION = "event-features-v3"
MODEL_FORMAT = "thermalwatch-event-classifier-v3"


def _value(observation: Any, key: str, default=None):
    return observation.get(key, default) if isinstance(observation, dict) else getattr(observation, key, default)


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _metadata(observation: Any) -> dict:
    value = _value(observation, "metadata_json") or _value(observation, "metadata") or {}
    if not isinstance(value, dict):
        return {}
    # Historical rows stored before metadata flattening may nest the original
    # FIRMS fields one level down. Preserve both layouts for live data.
    nested = value.get("metadata")
    return {**nested, **value} if isinstance(nested, dict) else value


def _numbers(observations: list[Any], key: str, *, metadata: bool = False) -> list[float]:
    values = []
    for observation in observations:
        value = _number(_metadata(observation).get(key) if metadata else _value(observation, key))
        if value is not None:
            values.append(value)
    return values


def extract_event_features(observations: Iterable[Any], persistence: dict | None = None,
                           context: dict | None = None) -> dict[str, float | None]:
    """Missing measurements and unverified context remain null in the API."""
    observations = list(observations)
    persistence = persistence if persistence is not None else compute_persistence_score(observations)
    context = context or {}
    intensities = _numbers(observations, "intensity")
    confidences = _numbers(observations, "confidence")
    frps = _numbers(observations, "frp", metadata=True)
    secondary = [_number(_metadata(o).get("bright_ti5", _metadata(o).get("bright_t31"))) for o in observations]
    secondary = [value for value in secondary if value is not None]
    scans = _numbers(observations, "scan", metadata=True)
    tracks = _numbers(observations, "track", metadata=True)
    daynight = [str(_metadata(o).get("daynight", "")).upper() for o in observations]
    known_daynight = [value for value in daynight if value in {"D", "N"}]
    timestamps = [ts for o in observations if (ts := _timestamp(_value(o, "timestamp"))) is not None]
    coordinates = [(lat, lon) for o in observations
                   if (lat := _number(_value(o, "latitude"))) is not None
                   and (lon := _number(_value(o, "longitude"))) is not None]
    spread = None
    if len(coordinates) >= 2:
        center_lat = mean(lat for lat, _ in coordinates)
        center_lon = mean(lon for _, lon in coordinates)
        spread = max(sqrt((111.2 * (lat - center_lat)) ** 2 +
                          (111.2 * cos(radians(center_lat)) * (lon - center_lon)) ** 2)
                     for lat, lon in coordinates)
    features = {
        "observation_count": float(len(observations)),
        "active_days": _number(persistence.get("active_days")),
        "persistence_score": _number(persistence.get("persistence_score")),
        "duration_hours": (max(timestamps) - min(timestamps)).total_seconds() / 3600 if len(timestamps) >= 2 else None,
        "temporal_trend": {"DECREASING": -1.0, "STABLE": 0.0, "INCREASING": 1.0}.get(persistence.get("trend")),
        "spatial_stability": _number(persistence.get("spatial_stability")),
        "mean_intensity": mean(intensities) if intensities else None,
        "max_intensity": max(intensities) if intensities else None,
        "intensity_variance": pvariance(intensities) if len(intensities) >= 2 else None,
        "mean_confidence": mean(confidences) if confidences else None,
        "mean_frp": mean(frps) if frps else None,
        "max_frp": max(frps) if frps else None,
        "frp_variance": pvariance(frps) if len(frps) >= 2 else None,
        "mean_secondary_brightness": mean(secondary) if secondary else None,
        "mean_scan": mean(scans) if scans else None,
        "mean_track": mean(tracks) if tracks else None,
        "night_fraction": known_daynight.count("N") / len(known_daynight) if known_daynight else None,
        "spatial_spread_km": spread,
        "recurrence_days": float(len({ts.date() for ts in timestamps})) if timestamps else None,
        "historical_activity": _number(context.get("historical_activity")),
        "facility_distance_km": _number(context.get("facility_distance_km")),
    }
    return {name: features[name] for name in FEATURE_NAMES}


def feature_vector(features: dict[str, float | None]) -> list[float]:
    return [features[name] if features[name] is not None else float("nan") for name in FEATURE_NAMES]


@lru_cache(maxsize=4)
def load_model(path: str) -> dict | None:
    """Only load a trusted local joblib artifact; never accept model uploads."""
    if not path or not Path(path).is_file():
        return None
    try:
        artifact = joblib.load(path)
        if artifact.get("format") != MODEL_FORMAT or tuple(artifact.get("feature_names", ())) != FEATURE_NAMES:
            raise ValueError("Incompatible event classifier artifact")
        model = artifact["model"]
        if artifact.get("training_type") == "UNSUPERVISED_FIRMS":
            if not hasattr(model, "decision_function"):
                raise ValueError("Artifact lacks a fitted anomaly detector")
        elif not hasattr(model, "predict_proba") or not hasattr(model, "classes_"):
            raise ValueError("Artifact lacks a fitted probabilistic classifier")
        return artifact
    except Exception as exc:
        logger.warning("ML model unavailable at %s: %s", path, exc)
        return None


def model_status(*, demo: bool = False) -> dict:
    artifact = load_model(settings.ML_MODEL_PATH) if settings.ML_MODEL_PATH else None
    if artifact is None or (demo and artifact.get("training_type") != "WEAK_LABEL_SYNTHETIC") or (
        not demo and artifact.get("training_type") == "WEAK_LABEL_SYNTHETIC"
    ):
        return {"status": "RULE_BASED_FALLBACK", "model_type": "rules", "version": None,
                "training_type": None, "training_source": None, "feature_version": FEATURE_VERSION,
                "calibrated": False, "validated": False, "fallback_active": True,
                "feature_names": FEATURE_NAMES, "note": "No eligible trusted model loaded."}
    unsupervised = artifact.get("training_type") == "UNSUPERVISED_FIRMS"
    return {"status": "WEAK_LABEL_PROTOTYPE" if demo else "UNSUPERVISED_PROTOTYPE" if unsupervised else "TRAINED_MODEL",
            "model_type": artifact.get("model_type", "RandomForestClassifier"),
            "version": artifact.get("version"), "training_type": artifact.get("training_type"),
            "training_source": artifact.get("label_provenance"),
            "feature_version": artifact.get("feature_version", FEATURE_VERSION),
            "calibrated": bool(artifact.get("calibrated", False)),
            "validated": bool(artifact.get("validated", False)), "fallback_active": False,
            "training_samples": artifact.get("training_samples"), "class_counts": artifact.get("class_counts"),
            "label_provenance": artifact.get("label_provenance"), "feature_names": FEATURE_NAMES,
            "note": "Synthetic weak labels; probabilities are not validated or calibrated." if demo else
            "Unsupervised anomaly ranking within one FIRMS capture; no ground-truth fire labels or probabilities." if unsupervised else
            "Supervised prototype; inspect independent evaluation before operational use."}


def classify_with_fallback(observations: Iterable[Any], persistence: dict | None = None,
                           *, allow_model: bool = True, demo: bool = False,
                           context: dict | None = None) -> dict:
    observations = list(observations)
    persistence = persistence if persistence is not None else compute_persistence_score(observations)
    features = extract_event_features(observations, persistence, context)
    status = model_status(demo=demo) if allow_model else {"status": "RULE_BASED_FALLBACK"}
    artifact = load_model(settings.ML_MODEL_PATH) if status["status"] != "RULE_BASED_FALLBACK" else None
    if artifact is None:
        baseline = classify_event(persistence, observations)
        return {**baseline, "is_ml": False, "model_status": "RULE_BASED_FALLBACK",
                "methodology": "Rule-based heuristic; no eligible trained model loaded",
                "features": features, "feature_importance": None,
                "top_contributing_features": [], "model_version": None,
                "data_mode": "DEMO DATA" if demo else "LIVE MODE"}

    model = artifact["model"]
    vector = feature_vector(features)
    if artifact.get("training_type") == "UNSUPERVISED_FIRMS":
        selected = [vector[index] for index in artifact["selected_feature_indices"]]
        score = float(model.decision_function([selected])[0])
        anomalous = bool(model.predict([selected])[0] == -1)

        contributions = []
        reasoning = []
        medians = artifact.get("feature_medians", {})
        p90 = artifact.get("feature_p90", {})

        max_frp = features.get("max_frp")
        if max_frp is not None and max_frp > p90.get("max_frp", 6.0):
            contributions.append({"feature": "max_frp", "value": max_frp, "probability_change": round((max_frp - medians.get("max_frp", 2.0)) / max(1.0, medians.get("max_frp", 2.0)), 3)})
            reasoning.append(f"Unusually high fire radiative power (Peak FRP: {max_frp:.1f} MW vs capture median {medians.get('max_frp', 2.1):.1f} MW)")

        active_days = features.get("active_days")
        if active_days is not None and active_days > 1:
            contributions.append({"feature": "active_days", "value": active_days, "probability_change": float(active_days)})
            reasoning.append(f"Multi-day temporal persistence ({int(active_days)} active days observed across satellite overpasses)")

        obs_count = features.get("observation_count")
        if obs_count is not None and obs_count > p90.get("observation_count", 3.0):
            contributions.append({"feature": "observation_count", "value": obs_count, "probability_change": float(obs_count)})
            reasoning.append(f"High detection cluster density ({int(obs_count)} detections clustered in spatial footprint)")

        max_int = features.get("max_intensity")
        if max_int is not None and max_int > p90.get("max_intensity", 340.0):
            contributions.append({"feature": "max_intensity", "value": max_int, "probability_change": round(max_int - medians.get("max_intensity", 330.0), 1)})
            reasoning.append(f"Elevated peak brightness temperature ({max_int:.1f} K)")

        night_fraction = features.get("night_fraction")
        if night_fraction is not None and night_fraction >= 0.5:
            contributions.append({"feature": "night_fraction", "value": night_fraction, "probability_change": float(night_fraction)})
            reasoning.append(f"Predominantly nocturnal thermal detection ({int(night_fraction * 100)}% night satellite passes)")

        duration_hours = features.get("duration_hours")
        if duration_hours is not None and duration_hours > p90.get("duration_hours", 12.0):
            contributions.append({"feature": "duration_hours", "value": duration_hours, "probability_change": round(duration_hours, 1)})
            reasoning.append(f"Extended temporal duration ({duration_hours:.1f} hours span)")

        if not reasoning:
            if anomalous:
                reasoning.append("Multi-feature thermal and spatial combination deviates from the typical 92% envelope of this FIRMS capture")
            else:
                reasoning.append("Thermal intensity and detection footprint fall within normal variation of this FIRMS capture")
        reasoning.append("Unsupervised anomaly score indicates relative statistical deviation; it does not determine fire cause or causality")

        return {
            "classification": "anomalous_thermal_pattern" if anomalous else "within_capture_range",
            "confidence": None, "probabilities": {}, "anomaly_score": round(score, 6),
            "reasoning": reasoning,
            "is_ml": True, "model_status": "UNSUPERVISED_PROTOTYPE",
            "methodology": "Isolation Forest unsupervised anomaly ranking (100 estimators, 8% outlier threshold); trained on unlabelled FIRMS capture",
            "features": features, "feature_importance": None,
            "top_contributing_features": contributions,
            "model_version": artifact.get("version"),
            "label_provenance": artifact.get("label_provenance"),
            "data_mode": "FIRMS SNAPSHOT" if settings.FIRMS_SNAPSHOT_PATH else "LIVE MODE",
        }
    probabilities = model.predict_proba([vector])[0]
    scores = {str(label): round(float(probability), 6) for label, probability in zip(model.classes_, probabilities)}
    predicted = max(scores, key=scores.get)
    estimator = model.named_steps.get("classifier") if hasattr(model, "named_steps") else model
    importance = getattr(estimator, "feature_importances_", None)
    # Local sensitivity against training medians; this is not a causal claim.
    contributions = []
    medians = artifact.get("feature_medians", {})
    class_index = list(model.classes_).index(predicted)
    for index, name in enumerate(FEATURE_NAMES):
        if features[name] is None or medians.get(name) is None:
            continue
        comparison = vector.copy()
        comparison[index] = medians[name]
        delta = float(probabilities[class_index] - model.predict_proba([comparison])[0][class_index])
        if delta > 0.001:
            contributions.append({"feature": name, "value": features[name], "probability_change": round(delta, 4)})
    contributions.sort(key=lambda item: item["probability_change"], reverse=True)
    return {
        "classification": predicted, "confidence": scores[predicted], "probabilities": scores,
        "reasoning": [f"{item['feature'].replace('_', ' ')} influenced this prototype estimate"
                      for item in contributions[:3]] or ["Available event features informed this prototype estimate."],
        "is_ml": True, "model_status": status["status"],
        "methodology": "Synthetic weak-label Random Forest prototype; unvalidated probabilities" if demo else
                       "Supervised Random Forest prototype; uncalibrated probabilities",
        "features": features,
        "feature_importance": {name: round(float(weight), 6) for name, weight in zip(FEATURE_NAMES, importance)} if importance is not None else None,
        "top_contributing_features": contributions[:3],
        "model_version": artifact.get("version"), "label_provenance": artifact.get("label_provenance"),
        "data_mode": "DEMO DATA" if demo else "LIVE MODE",
    }

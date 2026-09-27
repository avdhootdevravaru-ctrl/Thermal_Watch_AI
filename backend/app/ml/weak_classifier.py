"""First-day FIRMS recurrence classifier, separate from anomaly and risk.

The target is an observed later-day detection in the same event cluster. It is
not a fire-cause label or a calibrated prediction of future fire.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import joblib

from app.config import settings
from app.ml.classifier import FEATURE_VERSION, _value, extract_event_features

logger = logging.getLogger(__name__)

WEAK_MODEL_FORMAT = "ignis-firms-recurrence-v1"
WEAK_FEATURE_VERSION = f"{FEATURE_VERSION}-first-day-v2"
WEAK_FEATURE_NAMES = (
    "observation_count", "temporal_trend", "spatial_stability",
    "mean_intensity", "max_intensity", "intensity_variance", "mean_frp", "max_frp",
    "frp_variance", "mean_secondary_brightness", "mean_scan", "mean_track",
    "night_fraction", "spatial_spread_km",
)
CLASS_NAMES = ("multi_day_recurrence", "single_day_observed")
LABEL_STRATEGY = (
    "For eligible events first observed at least two calendar days before the capture's "
    "latest observation, label multi_day_recurrence when that event has a detection on "
    "a later date; otherwise label single_day_observed. Only first-day measurements "
    "enter the model. Satellite non-detection is not proof that heat ceased."
)


def first_day_features(observations: Iterable[Any]) -> dict[str, float | None]:
    """Use only data available on the event's first observed calendar day."""
    rows = list(observations)
    dated = [(row, ts) for row in rows if (ts := _local_timestamp(_value(row, "timestamp"))) is not None]
    if not dated:
        raise ValueError("Event has no valid observation timestamps")
    first_date = min(ts.date() for _, ts in dated)
    first_rows = [row for row, ts in dated if ts.date() == first_date]
    all_features = extract_event_features(first_rows)
    return {name: all_features[name] for name in WEAK_FEATURE_NAMES}


def _local_timestamp(value: Any) -> datetime | None:
    """Preserve the acquisition calendar date encoded by the FIRMS feed."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def weak_vector(features: dict[str, float | None]) -> list[float]:
    return [float("nan") if features[name] is None else float(features[name]) for name in WEAK_FEATURE_NAMES]


@lru_cache(maxsize=4)
def _load_validated(path: str, mtime_ns: int, size: int) -> dict | None:
    del mtime_ns, size
    try:
        artifact = joblib.load(path)  # Trusted local path only; never user-uploaded bytes.
        if artifact.get("format") != WEAK_MODEL_FORMAT:
            raise ValueError("Wrong artifact format")
        if tuple(artifact.get("feature_names", ())) != WEAK_FEATURE_NAMES:
            raise ValueError("Feature schema mismatch")
        if artifact.get("feature_version") != WEAK_FEATURE_VERSION:
            raise ValueError("Feature version mismatch")
        model = artifact["model"]
        if not hasattr(model, "predict_proba") or tuple(sorted(model.classes_)) != CLASS_NAMES:
            raise ValueError("Missing fitted classifier or unexpected classes")
        artifact["artifact_hash"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return artifact
    except Exception as exc:
        logger.warning("Weak FIRMS classifier unavailable: %s", type(exc).__name__)
        return None


def load_weak_model(path: str | None = None) -> dict | None:
    location = Path(path or settings.ML_CLASSIFIER_PATH)
    if not location.is_file():
        return None
    stat = location.stat()
    return _load_validated(str(location.resolve()), stat.st_mtime_ns, stat.st_size)


def weak_model_status(path: str | None = None) -> dict:
    location = Path(path or settings.ML_CLASSIFIER_PATH)
    artifact = load_weak_model(str(location))
    if artifact is None:
        return {
            "model_loaded": False, "artifact_available": location.is_file(),
            "inference_available": False, "model_name": "Unavailable",
            "model_version": None, "feature_version": WEAK_FEATURE_VERSION,
            "feature_names": WEAK_FEATURE_NAMES, "label_strategy": LABEL_STRATEGY,
            "training_dataset": None, "trained_at": None, "artifact_hash": None,
            "evaluation_metrics": None,
            "note": "No compatible trusted real-FIRMS classifier artifact is loaded.",
        }
    return {
        "model_loaded": True, "artifact_available": True, "inference_available": True,
        "model_name": artifact["model_type"], "model_version": artifact["version"],
        "feature_version": artifact["feature_version"], "feature_names": WEAK_FEATURE_NAMES,
        "label_strategy": artifact["label_strategy"],
        "training_dataset": artifact["training_dataset"],
        "training_samples": artifact["training_samples"],
        "eligible_samples": artifact["eligible_samples"],
        "holdout_samples": artifact["holdout_samples"],
        "class_counts": artifact["class_counts"],
        "dataset_fingerprint": artifact["dataset_fingerprint"],
        "trained_at": artifact["trained_at"], "artifact_hash": artifact["artifact_hash"],
        "evaluation_metrics": artifact["evaluation"], "random_seed": artifact["random_seed"],
        "note": "Held-out metrics measure observation-derived recurrence labels within one capture, not fire-cause accuracy or independent field validation.",
    }


def predict_weak(event_id: int, observations: Iterable[Any], *,
                 anomaly_score: float | None = None, capture_hash: str | None = None) -> dict:
    artifact = load_weak_model()
    if artifact is None:
        raise LookupError("No compatible real-FIRMS classifier artifact is loaded")
    features = first_day_features(observations)
    vector = weak_vector(features)
    model = artifact["model"]
    scores = model.predict_proba([vector])[0]
    classes = [str(item) for item in model.classes_]
    prediction = str(model.predict([vector])[0])
    class_index = classes.index(prediction)
    medians = artifact["feature_medians"]
    contributions = []
    for index, name in enumerate(WEAK_FEATURE_NAMES):
        value = features[name]
        median = medians.get(name)
        if value is None or median is None:
            continue
        comparison = vector.copy()
        comparison[index] = median
        delta = float(scores[class_index] - model.predict_proba([comparison])[0][class_index])
        contributions.append({
            "feature": name, "value": value, "training_median": median,
            "model_score_change": round(delta, 5),
            "interpretation": "First-day feature contribution estimated by replacing it with the training median; not causal.",
        })
    contributions.sort(key=lambda item: abs(item["model_score_change"]), reverse=True)
    warnings = [
        "Weak labels describe later satellite re-detection in one capture; they do not identify wildfire or industrial cause.",
        "Model class scores are uncalibrated and are not real-world fire probabilities.",
        "The held-out set is small and drawn from the same capture; external validation is unavailable.",
    ]
    if capture_hash and capture_hash != artifact["capture_hash"]:
        warnings.append("Current FIRMS capture differs from the classifier's training capture.")
    membership = ("training" if event_id in artifact["training_event_ids"] else
                  "held_out" if event_id in artifact["holdout_event_ids"] else "outside_training_cohort")
    return {
        "event_id": event_id, "model_name": artifact["model_type"],
        "model_version": artifact["version"], "model_status": "WEAKLY_SUPERVISED",
        "target": "Later-day re-detection of the same thermal event cluster",
        "prediction": prediction, "prediction_probability_if_calibrated": None,
        "uncalibrated_model_scores": {name: round(float(score), 6) for name, score in zip(classes, scores)},
        "anomaly_score_if_available": anomaly_score,
        "feature_values": features, "top_contributing_features": contributions[:5],
        "feature_importance": artifact["feature_importance"],
        "model_provenance": {
            "artifact_hash": artifact["artifact_hash"], "feature_version": artifact["feature_version"],
            "training_dataset_fingerprint": artifact["dataset_fingerprint"],
            "training_capture_hash": artifact["capture_hash"],
            "trained_at": artifact["trained_at"], "label_strategy": artifact["label_strategy"],
            "evaluation_role": membership, "random_seed": artifact["random_seed"],
        },
        "warnings": warnings,
    }

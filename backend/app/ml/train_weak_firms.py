"""Train a reproducible weak-label recurrence classifier on real FIRMS events.

Run from backend: python -m app.ml.train_weak_firms
The target is later-day satellite re-detection, not fire type or cause.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from math import floor
from typing import Any, Iterable

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, classification_report,
                             confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score, average_precision_score)
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold, cross_val_score
from sklearn.metrics import make_scorer
from sklearn.pipeline import Pipeline

from app.config import settings
from app.ml.weak_classifier import (CLASS_NAMES, LABEL_STRATEGY, WEAK_FEATURE_NAMES,
                                    WEAK_FEATURE_VERSION, WEAK_MODEL_FORMAT,
                                    _local_timestamp, first_day_features, weak_vector)
from app.snapshot import snapshot_state
from app.ml.classifier import _value
from app.processing.clustering import cluster_observations

SEED = 42


def build_training_dataset(events: Iterable[dict], latest_date: date) -> list[dict[str, Any]]:
    """Exclude events without a full following calendar day of observation window."""
    rows = []
    cutoff = latest_date - timedelta(days=2)
    for event in events:
        observations = event.get("observations") or []
        dates = [ts.date() for observation in observations
                 if (ts := _local_timestamp(observation.get("timestamp") if isinstance(observation, dict)
                                           else getattr(observation, "timestamp", None))) is not None]
        if not dates or min(dates) > cutoff:
            continue
        first_rows = [row for row in observations if (ts := _local_timestamp(_value(row, "timestamp"))) and ts.date() == min(dates)]
        points = [{key: _value(row, key) for key in ("latitude", "longitude", "timestamp")} for row in first_rows]
        # Reject full-capture clusters whose initial members only became linked
        # through future detections. Feature membership must exist on day one.
        if len(cluster_observations(points)) != 1:
            continue
        try:
            features = first_day_features(observations)
        except ValueError:
            continue
        label = "multi_day_recurrence" if any(day > min(dates) for day in dates) else "single_day_observed"
        group = (floor(np.mean([point["latitude"] for point in points])),
                 floor(np.mean([point["longitude"] for point in points])))
        rows.append({"event_id": int(event["id"]), "features": features, "label": label,
                     "spatial_group": f"{group[0]}:{group[1]}", "first_date": min(dates).isoformat()})
    return sorted(rows, key=lambda row: row["event_id"])


def train(output: Path) -> dict:
    if settings.DEMO_MODE or not settings.FIRMS_SNAPSHOT_PATH:
        raise ValueError("Real FIRMS snapshot mode is required for weak-label training")
    state = snapshot_state()
    latest = _local_timestamp(state["validation"].get("latest_observation"))
    if latest is None:
        raise ValueError("Capture has no valid latest observation")
    rows = build_training_dataset(state["events"].values(), latest.date())
    counts = Counter(row["label"] for row in rows)
    if len(rows) < 40 or any(counts[name] < 8 for name in CLASS_NAMES):
        raise ValueError(f"Too few eligible real events or minority labels for training: {dict(counts)}")

    vectors = np.asarray([weak_vector(row["features"]) for row in rows], dtype=float)
    labels = np.asarray([row["label"] for row in rows])
    
    groups = np.asarray([row["spatial_group"] for row in rows])
    train_indices, test_indices = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=SEED).split(vectors, labels, groups))
    
    train_x, train_y = vectors[train_indices], labels[train_indices]
    test_x, test_y = vectors[test_indices], labels[test_indices]
    if len(set(train_y)) != 2 or len(set(test_y)) != 2:
        raise ValueError("Fixed geographic holdout lacks both labels; collect more data")
    
    models = {
        "RandomForest": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("classifier", RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=SEED))
        ]),
        "HistGradientBoosting": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("classifier", HistGradientBoostingClassifier(class_weight="balanced", random_state=SEED))
        ]),
        "LogisticRegression": Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(class_weight="balanced", random_state=SEED, max_iter=1000))
        ])
    }
    
    best_f1 = -1
    best_model_name = ""
    best_estimator = None
    
    positive = "multi_day_recurrence"
    cv = list(StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=SEED).split(train_x, train_y, groups[train_indices]))
    if any(len(set(train_y[a])) != 2 or len(set(train_y[b])) != 2 for a, b in cv):
        raise ValueError("Training geographic folds lack both labels; collect more data")
    comparisons = {}
    
    for name, pipeline in models.items():
        scores = cross_val_score(pipeline, train_x, train_y, cv=cv,
                                scoring=make_scorer(f1_score, pos_label=positive, zero_division=0), error_score="raise")
        f1 = float(scores.mean())
        comparisons[name] = {"mean_training_cv_f1": f1, "fold_f1": scores.tolist()}
        if f1 > best_f1:
            best_f1 = f1
            best_model_name = name
            best_estimator = pipeline
            
    estimator = best_estimator
    estimator.fit(train_x, train_y)
    predictions = estimator.predict(test_x)
    probabilities = estimator.predict_proba(test_x)
    pos_idx = list(estimator.classes_).index(positive)
    pos_probs = probabilities[:, pos_idx]
    
    roc_auc = roc_auc_score(test_y == positive, pos_probs)
    pr_auc = average_precision_score(test_y == positive, pos_probs)
    
    evaluation = {
        "scope": "Untouched geographic group holdout within one FIRMS capture; not temporal validation",
        "split_method": "Fixed seed 42, 1-degree first-day centroid cells; 25% of groups held out",
        "selection_method": "Three-fold geographic group CV on training records only; highest recurrence F1",
        "model_comparison": comparisons,
        "holdout_size": len(test_indices),
        "accuracy": float(accuracy_score(test_y, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(test_y, predictions)),
        "precision_positive": float(precision_score(test_y, predictions, pos_label=positive, zero_division=0)),
        "recall_positive": float(recall_score(test_y, predictions, pos_label=positive, zero_division=0)),
        "f1_positive": float(f1_score(test_y, predictions, pos_label=positive, zero_division=0)),
        "f1_macro": float(f1_score(test_y, predictions, average="macro", zero_division=0)),
        "roc_auc": float(roc_auc),
        "pr_auc": float(pr_auc),
        "class_order": list(CLASS_NAMES),
        "confusion_matrix": confusion_matrix(test_y, predictions, labels=CLASS_NAMES).tolist(),
        "per_class": classification_report(test_y, predictions, labels=CLASS_NAMES,
                                           output_dict=True, zero_division=0),
        "limitations": [
            "Labels are derived from later observations in the same capture, not independent fire-cause review.",
            "The small same-capture geographic holdout does not establish future-capture generalization; nearby cells may remain correlated.",
            "Events requiring future detections to connect their first-day members are excluded; labels remain retrospective cluster re-detection.",
            "A single-day observation can reflect satellite revisit limits, cloud, or capture timing rather than source cessation.",
            "If metrics remain poor, it indicates weak signal in the feature set for this label definition."
        ],
    }
    
    medians = {
        name: float(np.median(finite)) if len(finite) else None
        for index, name in enumerate(WEAK_FEATURE_NAMES)
        for finite in [train_x[np.isfinite(train_x[:, index]), index]]
    }
    
    classifier_step = estimator.named_steps["classifier"]
    if hasattr(classifier_step, "feature_importances_"):
        importance = classifier_step.feature_importances_
    elif hasattr(classifier_step, "coef_"):
        importance = np.abs(classifier_step.coef_[0])
    else:
        from sklearn.inspection import permutation_importance
        perm = permutation_importance(estimator, train_x, train_y, n_repeats=5, random_state=42)
        raw_imp = np.maximum(0, perm.importances_mean)
        importance = raw_imp / raw_imp.sum() if raw_imp.sum() > 0 else raw_imp
        
    feature_importance = {name: round(float(weight), 6) for name, weight in zip(WEAK_FEATURE_NAMES, importance)}
    
    dataset_bytes = json.dumps(rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    fingerprint = hashlib.sha256(dataset_bytes).hexdigest()
    capture_hash = hashlib.sha256(Path(settings.FIRMS_SNAPSHOT_PATH).read_bytes()).hexdigest()
    
    artifact = {
        "format": WEAK_MODEL_FORMAT, "model": estimator,
        "model_type": best_model_name, "version": f"firms-recurrence-v2-{fingerprint[:8]}",
        "feature_version": WEAK_FEATURE_VERSION, "feature_names": WEAK_FEATURE_NAMES,
        "feature_medians": medians,
        "feature_importance": feature_importance,
        "label_strategy": LABEL_STRATEGY, "class_names": CLASS_NAMES,
        "training_dataset": f"Validated {state['source']} local FIRMS capture; first-day event measurements",
        "dataset_fingerprint": fingerprint, "capture_hash": capture_hash,
        "trained_at": datetime.now(timezone.utc).isoformat(), "random_seed": SEED,
        "eligible_samples": len(rows), "training_samples": len(train_indices),
        "holdout_samples": len(test_indices), "class_counts": dict(counts),
        "training_event_ids": [rows[index]["event_id"] for index in train_indices],
        "holdout_event_ids": [rows[index]["event_id"] for index in test_indices],
        "training_groups": sorted(set(groups[train_indices])),
        "holdout_groups": sorted(set(groups[test_indices])),
        "evaluation": evaluation, "calibrated": False, "independently_validated": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output, compress=3)
    artifact_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    artifact["artifact_hash"] = artifact_hash
    metadata = {key: value for key, value in artifact.items() if key != "model"}
    metadata_path = output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    
    return {"artifact_path": str(output), "metadata_path": str(metadata_path),
            "model_version": artifact["version"], "model_type": best_model_name, 
            "eligible_samples": len(rows),
            "training_samples": len(train_indices), "holdout_samples": len(test_indices),
            "class_counts": dict(counts), "artifact_hash": artifact_hash,
            "dataset_fingerprint": fingerprint, "evaluation": evaluation,
            "feature_importance": feature_importance}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(settings.ML_CLASSIFIER_PATH))
    args = parser.parse_args()
    print(json.dumps(train(args.output), indent=2))


if __name__ == "__main__":
    main()


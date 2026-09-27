"""Reproducible synthetic weak-label model for the *demo only*.

The labels are generated from deliberately distinct temporal patterns. They
are not field truth, cannot identify a fire cause, and yield no accuracy claim.
The live API refuses to use this artifact.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from app.ml.classifier import FEATURE_NAMES, FEATURE_VERSION, MODEL_FORMAT, extract_event_features, feature_vector

SEED = 26162
LABEL_PATTERNS = {
    "persistent_thermal_source": (12, 25, 4, 9, 350, 390),
    "temporary_thermal_event": (3, 9, 1, 3, 315, 350),
    "unknown": (1, 2, 1, 1, 295, 330),
}


def weak_label_records(per_class: int = 60) -> list[dict]:
    if per_class < 10:
        raise ValueError("At least 10 synthetic patterns per class are required")
    rng = Random(SEED)
    anchor = datetime(2026, 9, 1, tzinfo=timezone.utc)
    records = []
    for label, (low_count, high_count, low_days, high_days, low_temp, high_temp) in LABEL_PATTERNS.items():
        for _ in range(per_class):
            count = rng.randint(low_count, high_count)
            days = rng.randint(low_days, high_days)
            lat, lon = rng.uniform(8, 32), rng.uniform(70, 94)
            intensity = rng.uniform(low_temp, high_temp)
            observations = []
            for index in range(count):
                observations.append({
                    "timestamp": (anchor + timedelta(days=index % days, hours=index // days)).isoformat(),
                    "latitude": lat + rng.uniform(-0.002, 0.002),
                    "longitude": lon + rng.uniform(-0.002, 0.002),
                    "intensity": round(intensity + rng.uniform(-8, 8), 2),
                    "confidence": round(rng.uniform(45, 95), 1),
                    "source": "DEMO_SYNTHETIC",
                    "metadata": {"frp": round(rng.uniform(4, 40), 2)},
                })
            records.append({"label": label, "observations": observations})
    return records


def train_weak_demo_model(output: Path, per_class: int = 60) -> dict:
    records = weak_label_records(per_class)
    vectors = [feature_vector(extract_event_features(record["observations"])) for record in records]
    labels = [record["label"] for record in records]
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("classifier", RandomForestClassifier(n_estimators=100, random_state=SEED, n_jobs=1)),
    ])
    model.fit(vectors, labels)
    matrix = np.array(vectors, dtype=float)
    medians = {name: float(np.nanmedian(matrix[:, index])) if np.isfinite(matrix[:, index]).any() else None
               for index, name in enumerate(FEATURE_NAMES)}
    artifact = {
        "format": MODEL_FORMAT, "version": "demo-weak-v2", "model": model,
        "model_type": "RandomForestClassifier", "feature_version": FEATURE_VERSION,
        "calibrated": False, "validated": False,
        "feature_names": FEATURE_NAMES, "feature_medians": medians,
        "training_type": "WEAK_LABEL_SYNTHETIC",
        "label_provenance": "Deterministic synthetic temporal patterns; no field labels",
        "training_samples": len(labels), "class_counts": dict(Counter(labels)),
        "seed": SEED,
        "label_rules": "Persistent: 12–25 detections across 4–9 days; temporary: 3–9 across 1–3 days; unknown: 1–2 in one day.",
        "evaluation": None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output)
    return {"output": str(output), "version": artifact["version"],
            "training_samples": len(labels), "class_counts": artifact["class_counts"],
            "warning": "Demo-only weak-label prototype. Probabilities are unvalidated and uncalibrated."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/demo_weak_classifier.joblib"))
    parser.add_argument("--per-class", type=int, default=60)
    args = parser.parse_args()
    print(json.dumps(train_weak_demo_model(args.output, args.per_class), indent=2))


if __name__ == "__main__":
    main()

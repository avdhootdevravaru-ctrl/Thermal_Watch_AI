"""Train an optional classifier from independently labeled event JSONL.

Each line must contain {"label": <Classification enum value>, "observations": [...]}
and labels must come from review independent of ThermalWatch's rule engine.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from app.db.models import Classification
from app.ml.classifier import FEATURE_NAMES, FEATURE_VERSION, MODEL_FORMAT, extract_event_features, feature_vector

ALLOWED_LABELS = {member.value for member in Classification if member is not Classification.UNKNOWN}


def prepare_dataset(path: Path) -> tuple[list[list[float]], list[str]]:
    vectors, labels = [], []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            label = record.get("label")
            observations = record.get("observations")
            if label not in ALLOWED_LABELS or not isinstance(observations, list) or not observations:
                raise ValueError(f"Line {line_number}: expected a supported independently labeled event and nonempty observations")
            vectors.append(feature_vector(extract_event_features(observations)))
            labels.append(label)
    return vectors, labels


def train_model(dataset: Path, output: Path, label_provenance: str) -> dict:
    if not label_provenance.strip() or label_provenance.lower().startswith(("demo", "synthetic", "rule")):
        raise ValueError("Specify an independent label provenance; synthetic or rule-generated labels are not accepted")
    vectors, labels = prepare_dataset(dataset)
    counts = dict(Counter(labels))
    if len(vectors) < 30 or len(counts) < 2 or min(counts.values()) < 10:
        raise ValueError("Training requires at least 30 independently labeled events and at least 10 per class")
    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("classifier", RandomForestClassifier(n_estimators=100, class_weight="balanced",
                                              random_state=42, n_jobs=1)),
    ])
    model.fit(vectors, labels)
    matrix = np.array(vectors, dtype=float)
    medians = {name: float(np.nanmedian(matrix[:, index])) if np.isfinite(matrix[:, index]).any() else None
               for index, name in enumerate(FEATURE_NAMES)}
    artifact = {"format": MODEL_FORMAT, "version": "supervised-prototype-v3", "model": model,
                "model_type": "RandomForestClassifier", "feature_version": FEATURE_VERSION,
                "calibrated": False, "validated": False,
                "feature_names": FEATURE_NAMES, "feature_medians": medians,
                "training_type": "INDEPENDENT_LABELS", "label_provenance": label_provenance,
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "training_samples": len(labels), "class_counts": counts}
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output)
    return {"output": str(output), "training_samples": len(labels), "class_counts": counts,
            "note": "Trained prototype only; no predictive accuracy is claimed without independent held-out evaluation."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path, help="JSONL of independently labeled events")
    parser.add_argument("--output", required=True, type=Path, help="Trusted local joblib artifact path")
    parser.add_argument("--label-provenance", required=True, help="Who independently verified the labels")
    args = parser.parse_args()
    print(json.dumps(train_model(args.dataset, args.output, args.label_provenance), indent=2))


if __name__ == "__main__":
    main()

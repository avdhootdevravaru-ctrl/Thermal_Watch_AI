"""Fit an honest, unlabelled anomaly prototype on a validated FIRMS capture.

Run from backend: python -m app.ml.train_anomaly
"""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from app.config import settings
from app.ml.classifier import FEATURE_NAMES, FEATURE_VERSION, MODEL_FORMAT, feature_vector
from app.snapshot import snapshot_state


def train(output: Path) -> dict:
    state = snapshot_state()
    events = list(state["events"].values())
    if len(events) < 20:
        raise ValueError("At least 20 validated event clusters are needed for anomaly training")
    vectors = [feature_vector(event["classification"]["features"]) for event in events]
    # Entirely missing context features are excluded rather than invented.
    selected = [index for index in range(len(FEATURE_NAMES))
                if any(vector[index] == vector[index] for vector in vectors)]
    matrix = [[vector[index] for index in selected] for vector in vectors]
    model = make_pipeline(SimpleImputer(strategy="median"),
                          IsolationForest(n_estimators=100, contamination=0.08, random_state=42))
    model.fit(matrix)

    import numpy as np
    feature_medians = {}
    feature_p90 = {}
    for index, name in enumerate(FEATURE_NAMES):
        vals = [vector[index] for vector in vectors if vector[index] == vector[index]]
        if vals:
            feature_medians[name] = float(np.median(vals))
            feature_p90[name] = float(np.percentile(vals, 90))

    # Keep the public 21-feature vector stable while selecting observed columns.
    artifact = {
        "format": MODEL_FORMAT, "feature_names": FEATURE_NAMES,
        "feature_version": FEATURE_VERSION, "selected_feature_indices": selected,
        "model": model, "training_type": "UNSUPERVISED_FIRMS",
        "model_type": "IsolationForest", "version": "firms-capture-v1",
        "training_samples": len(events), "calibrated": False, "validated": False,
        "feature_medians": feature_medians, "feature_p90": feature_p90,
        "label_provenance": f"Unlabelled NASA FIRMS {state['source']} India capture; acquired through {state['validation']['latest_observation']}",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("models/firms_anomaly.joblib"))
    args = parser.parse_args()
    result = train(args.output)
    print(f"Trained {result['model_type']} on {result['training_samples']} unlabelled FIRMS event clusters; saved {args.output}")

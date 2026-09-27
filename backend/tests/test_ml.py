"""Classification contracts; training data here is test-only, never a shipped model."""

import json
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.ml.classifier import FEATURE_NAMES, FEATURE_VERSION, classify_with_fallback, extract_event_features, load_model, model_status
from app.ml.train import prepare_dataset, train_model
from app.main import database_unavailable


def _observations(intensity: float, count: int = 3):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [{"timestamp": (now + timedelta(days=i)).isoformat(),
             "latitude": 21.1, "longitude": 79.0,
             "intensity": intensity + i, "confidence": 80,
             "metadata": {"frp": 10 + i}} for i in range(count)]


def test_feature_extraction_and_rule_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ML_MODEL_PATH", "")
    observations = _observations(350)
    features = extract_event_features(observations)
    assert tuple(features) == FEATURE_NAMES
    assert features["observation_count"] == 3
    assert features["mean_frp"] == 11
    assert features["historical_activity"] is None
    assert features["facility_distance_km"] is None
    assert features["mean_secondary_brightness"] is None
    assert features["spatial_stability"] is not None
    assert features["temporal_trend"] is None
    result = classify_with_fallback(observations)
    assert result["is_ml"] is False
    assert result["model_status"] == "RULE_BASED_FALLBACK"
    assert result["features"] == features
    status = model_status()
    assert status["feature_version"] == FEATURE_VERSION
    assert status["fallback_active"] is True
    assert status["validated"] is False


def test_missing_measurements_stay_null():
    features = extract_event_features([{"timestamp": "2026-01-01T00:00:00Z",
                                        "latitude": 21.1, "longitude": 79.0}])
    assert features["mean_intensity"] is None
    assert features["mean_frp"] is None
    assert features["duration_hours"] is None
    assert features["spatial_spread_km"] is None
    assert features["spatial_stability"] is None
    assert features["temporal_trend"] is None


def test_temporal_trend_and_spatial_variance_are_extracted():
    observations = _observations(300, count=4)
    observations[2]["intensity"] = 400
    observations[3]["intensity"] = 401
    features = extract_event_features(observations)
    assert features["temporal_trend"] == 1.0
    assert features["spatial_stability"] == 0.0


def test_training_requires_independent_labels(tmp_path):
    dataset = tmp_path / "small.jsonl"
    dataset.write_text(json.dumps({"label": "industrial_fire", "observations": _observations(390)}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at least 30"):
        train_model(dataset, tmp_path / "model.joblib", "independently reviewed test fixture")
    with pytest.raises(ValueError, match="independent label provenance"):
        train_model(dataset, tmp_path / "model.joblib", "synthetic demo labels")
    assert len(prepare_dataset(dataset)[0]) == 1


def test_train_serialize_load_and_predict_test_only(tmp_path, monkeypatch):
    dataset = tmp_path / "reviewed-test-fixture.jsonl"
    rows = []
    for index in range(30):
        label = "industrial_fire" if index < 15 else "agricultural_burning"
        rows.append({"label": label,
                     "observations": _observations(390 + index % 3 if index < 15 else 310 + index % 3)})
    dataset.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    artifact_path = tmp_path / "classifier.joblib"
    report = train_model(dataset, artifact_path, "independently reviewed test fixture")
    assert report["training_samples"] == 30
    assert artifact_path.is_file()
    assert load_model(str(artifact_path))["feature_names"] == FEATURE_NAMES
    monkeypatch.setattr(settings, "ML_MODEL_PATH", str(artifact_path))
    result = classify_with_fallback(_observations(392))
    assert result["is_ml"] is True
    assert result["model_status"] == "TRAINED_MODEL"
    assert result["classification"] in {"industrial_fire", "agricultural_burning"}
    assert abs(sum(result["probabilities"].values()) - 1) < 0.001


def test_database_failure_is_a_clean_service_response():
    response = asyncio.run(database_unavailable(None, OperationalError("SELECT 1", {}, Exception("offline"))))
    assert response.status_code == 503
    assert b"Database unavailable" in response.body
    assert b"Traceback" not in response.body

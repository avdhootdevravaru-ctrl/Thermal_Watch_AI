"""Test-only observations; production training reads the real FIRMS capture."""

from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timedelta, timezone

import joblib
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.evidence import evidence_package
from app.main import app
from app.ml.train_weak_firms import build_training_dataset, train
from app.ml.weak_classifier import (WEAK_FEATURE_NAMES, first_day_features,
                                    load_weak_model, predict_weak, weak_model_status)


def _event(event_id: int, *, recurrence: bool, first_day: int = 25) -> dict:
    start = datetime(2026, 9, first_day, 10, tzinfo=timezone.utc)
    observations = [{
        "timestamp": start + timedelta(minutes=index * 20),
        "latitude": 10.1 + event_id // 2, "longitude": 75.0,
        "intensity": 300.0 + event_id % 8 + index,
        "confidence": None, "source": "VIIRS_NOAA20_NRT",
        "metadata": {"frp": 1.0 + event_id % 6 + index, "daynight": "D"},
    } for index in range(1 + event_id % 3)]
    if recurrence:
        observations.append({
            **observations[0], "timestamp": start + timedelta(days=1),
            "intensity": 490.0, "metadata": {"frp": 900.0, "daynight": "N"},
        })
    return {"id": event_id, "observations": observations,
            "classification": {"anomaly_score": -0.1}}


def test_first_day_features_exclude_future_observations_and_invalid_time():
    event = _event(3, recurrence=True)
    features = first_day_features(event["observations"])
    assert tuple(features) == WEAK_FEATURE_NAMES
    assert features["max_intensity"] < 490
    assert features["max_frp"] < 900
    assert first_day_features(event["observations"][:-1]) == features
    with pytest.raises(ValueError, match="timestamps"):
        first_day_features([{"timestamp": "bad", "intensity": 300}])


def test_dataset_censors_events_without_full_followup():
    events = [_event(1, recurrence=True), _event(2, recurrence=False),
              _event(3, recurrence=True, first_day=26)]
    rows = build_training_dataset(events, datetime(2026, 9, 27).date())
    assert [row["event_id"] for row in rows] == [1, 2]
    assert [row["label"] for row in rows] == ["multi_day_recurrence", "single_day_observed"]


def test_real_pipeline_training_contract_and_api(tmp_path, monkeypatch):
    # Small deterministic fixture exercises training mechanics; the real CLI
    # uses snapshot_state() over validated NASA FIRMS rows.
    events = [_event(index, recurrence=index % 2 == 0) for index in range(1, 41)]
    capture = tmp_path / "capture.csv"
    capture.write_text("test-only capture fixture", encoding="utf-8")
    state = {"events": {event["id"]: event for event in events},
             "validation": {"latest_observation": "2026-09-27T02:00:00+00:00"},
             "source": "VIIRS_NOAA20_NRT"}
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "FIRMS_SNAPSHOT_PATH", str(capture))
    monkeypatch.setattr("app.ml.train_weak_firms.snapshot_state", lambda: state)
    monkeypatch.setattr("app.snapshot.snapshot_state", lambda: state)
    artifact_path = tmp_path / "classifier.joblib"
    monkeypatch.setattr(settings, "ML_CLASSIFIER_PATH", str(artifact_path))

    report = train(artifact_path)
    assert report["eligible_samples"] == 40
    assert report["training_samples"] + report["holdout_samples"] == 40
    assert artifact_path.is_file()
    assert report["artifact_hash"] == hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    assert report["evaluation"]["holdout_size"] == report["holdout_samples"]
    assert len(report["evaluation"]["confusion_matrix"]) == 2
    assert weak_model_status()["model_loaded"] is True
    artifact = joblib.load(artifact_path)
    assert not set(artifact["training_groups"]) & set(artifact["holdout_groups"])
    assert not set(artifact["training_event_ids"]) & set(artifact["holdout_event_ids"])
    repeated = train(tmp_path / "repeat.joblib")
    assert repeated["evaluation"] == report["evaluation"]
    assert repeated["dataset_fingerprint"] == report["dataset_fingerprint"]

    sample = events[0]
    inference = predict_weak(sample["id"], sample["observations"], anomaly_score=-0.1)
    assert inference["prediction"] in {"multi_day_recurrence", "single_day_observed"}
    assert inference["prediction_probability_if_calibrated"] is None
    assert inference["model_provenance"]["artifact_hash"] == report["artifact_hash"]
    assert inference["anomaly_score_if_available"] == -0.1
    assert all(item["feature"] in WEAK_FEATURE_NAMES for item in inference["top_contributing_features"])

    with TestClient(app) as client:
        get_response = client.get(f"/thermal-events/{sample['id']}/weak-classification")
        post_response = client.post("/classification", json={"event_id": sample["id"]})
        assert get_response.status_code == post_response.status_code == 200
        assert get_response.json()["prediction"] == post_response.json()["prediction"]
        assert client.get("/thermal-events/99999/weak-classification").status_code == 404
        status = client.get("/health/model").json()["weak_classifier"]
        assert status["artifact_hash"] == report["artifact_hash"]
        assert status["evaluation_metrics"]["holdout_size"] == report["holdout_samples"]

    old = copy.deepcopy(load_weak_model(str(artifact_path)))
    wrong_path = tmp_path / "wrong-schema.joblib"
    old["feature_names"] = ("wrong_feature",)
    joblib.dump(old, wrong_path)
    assert load_weak_model(str(wrong_path)) is None
    assert weak_model_status(str(tmp_path / "missing.joblib"))["model_loaded"] is False

    event_for_evidence = {**sample, "data_mode": "FIRMS SNAPSHOT",
                          "start_time": sample["observations"][0]["timestamp"],
                          "end_time": sample["observations"][-1]["timestamp"],
                          "persistence": {"active_days": 2},
                          "risk": {"score": 30, "severity": "MEDIUM", "factors": []},
                          "classification": {"classification": "within_capture_range",
                                             "model_status": "UNSUPERVISED_PROTOTYPE",
                                             "anomaly_score": -0.1}}
    # The evidence serializer accepts observation objects, like snapshot_state.
    from types import SimpleNamespace
    event_for_evidence["observations"] = [SimpleNamespace(
        **{**observation, "sensor": "VIIRS", "metadata_json": observation["metadata"]})
        for observation in sample["observations"]]
    package = evidence_package(event_for_evidence)
    assert package["sha256"] == evidence_package(event_for_evidence)["sha256"]
    assert package["payload"]["weak_classification"]["prediction"] == inference["prediction"]

    monkeypatch.setattr(settings, "ML_CLASSIFIER_PATH", str(tmp_path / "missing.joblib"))
    with TestClient(app) as client:
        assert client.get(f"/thermal-events/{sample['id']}/weak-classification").status_code == 503
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    with TestClient(app) as client:
        assert client.post("/classification", json={"event_id": sample["id"]}).status_code == 409

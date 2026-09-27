"""Demo responses stay explicit, coherent and independent of PostgreSQL."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.demo import router, _events
from app.ingestion.firms_client import FirmsClient
from app.ingestion.normalizer import normalize_observation
from app.ml.classifier import extract_event_features
from app.api.health import router as health_router
from app.config import settings


@pytest.fixture(autouse=True)
def force_synthetic_demo(monkeypatch):
    monkeypatch.setattr(settings, "FIRMS_SNAPSHOT_PATH", "")
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    _events.cache_clear()
    yield
    _events.cache_clear()


def test_demo_dashboard_and_event_pipeline(monkeypatch):
    monkeypatch.setattr(settings, "ML_MODEL_PATH", "")
    _events.cache_clear()
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    hotspots = client.get("/map/hotspots").json()
    events = client.get("/thermal-events").json()
    stats = client.get("/history/statistics").json()
    quality = client.get("/history/data-quality").json()

    assert hotspots["total"] == events["total"] == 7
    assert events["items"][0]["classification_type"]
    assert sum(hotspots["risk_summary"].values()) == 7
    assert all(hotspots["risk_summary"][level] > 0 for level in ("high", "medium", "low"))
    assert stats["total_observations"] == quality["total_observations"] == sum(
        event["observation_count"] for event in events["items"]
    )
    assert stats["data_mode"] == "DEMO DATA"

    event = client.get("/thermal-events/9001").json()
    risk = client.get("/thermal-events/9001/risk").json()
    classification = client.get("/thermal-events/9001/classification").json()
    profile = client.get("/history/event/9001/profile").json()
    assert len(event["observations"]) == event["observation_count"]
    assert all(obs["source"] == "DEMO_SYNTHETIC" for obs in event["observations"])
    assert risk["score"] >= 50 and risk["contributing_factors"]
    assert risk["classification"]["is_ml"] is False
    assert classification["model_status"] == "RULE_BASED_FALLBACK"
    assert profile["baseline_status"] == "INSUFFICIENT_HISTORY"


def test_demo_read_only_and_missing_event():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.post("/ingestion/firms/run").status_code == 409
    assert client.get("/thermal-events/123456").status_code == 404


def test_demo_health_exposes_database_and_model_mode(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    monkeypatch.setattr(settings, "ML_MODEL_PATH", "")
    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)
    assert client.get("/health").json()["classifier_status"] == "RULE_BASED_FALLBACK"
    assert client.get("/health/database").json() == {
        "status": "demo", "database": "not used", "data_mode": "DEMO DATA"}


def test_weak_label_demo_model_is_explicit_and_never_used_live(tmp_path, monkeypatch):
    from app.ml.bootstrap import train_weak_demo_model
    from app.ml.classifier import model_status

    artifact = tmp_path / "weak.joblib"
    report = train_weak_demo_model(artifact, per_class=10)
    assert report["training_samples"] == 30
    monkeypatch.setattr(settings, "ML_MODEL_PATH", str(artifact))
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    _events.cache_clear()
    app = FastAPI()
    app.include_router(router)
    app.include_router(health_router)
    client = TestClient(app)
    model_health = client.get("/health/model").json()
    assert model_health["status"] == "WEAK_LABEL_PROTOTYPE"
    assert model_health["feature_version"] == "event-features-v3"
    assert model_health["validated"] is False
    assert model_health["calibrated"] is False
    assert model_health["fallback_active"] is False
    classification = client.get("/thermal-events/9001/classification").json()
    assert classification["is_ml"] is True
    assert classification["model_status"] == "WEAK_LABEL_PROTOTYPE"
    assert classification["data_mode"] == "DEMO DATA"
    assert abs(sum(classification["probabilities"].values()) - 1) < 0.001
    assert model_status(demo=False)["status"] == "RULE_BASED_FALLBACK"
    _events.cache_clear()


def test_malformed_firms_rows_do_not_become_live_observations():
    csv = (
        "latitude,longitude,bright_ti4,acq_date,acq_time,confidence\n"
        "22.8,86.2,350,2026-09-26,1430,h\n"
        "bad,86.2,350,2026-09-26,1430,h\n"
        "22.8,86.2,350,not-a-date,1430,h\n"
    )
    rows = FirmsClient("unused")._parse_csv(csv, satellite="VIIRS_NOAA20_NRT")
    assert len(rows) == 1
    assert rows[0]["source"] == "VIIRS_NOAA20_NRT"
    assert normalize_observation({"latitude": "nan", "longitude": "86.2"})["_invalid_coordinates"]


def test_firms_optional_measurements_reach_feature_extraction():
    csv = (
        "latitude,longitude,bright_ti4,acq_date,acq_time,confidence,"
        "bright_ti5,frp,scan,track,daynight\n"
        "22.8,86.2,350,2026-09-26,1430,h,310,21.5,0.5,0.7,N\n"
    )
    parsed = FirmsClient("unused")._parse_csv(csv)
    normalized = normalize_observation(parsed[0])
    assert normalized["intensity"] == 350
    assert normalized["metadata"]["frp"] == "21.5"
    features = extract_event_features([normalized])
    assert features["mean_frp"] == 21.5
    assert features["mean_secondary_brightness"] == 310
    assert features["mean_scan"] == 0.5
    assert features["night_fraction"] == 1
    assert normalize_observation({"frp": "50", "timestamp": "2026-09-26T14:30:00Z"})["intensity"] is None


def test_firms_area_contract_and_modis_brightness():
    assert FirmsClient("unused", area="IND", days=5).area == "68,6.5,97.5,35.5"
    with pytest.raises(ValueError, match="1–5"):
        FirmsClient("unused", days=10)
    with pytest.raises(ValueError, match="west,south,east,north"):
        FirmsClient("unused", area="not-an-area")
    csv = "latitude,longitude,brightness,frp,acq_date,acq_time,confidence\n22.8,86.2,330,17.2,2026-09-26,1430,80\n"
    parsed = FirmsClient("unused")._parse_csv(csv, satellite="MODIS_NRT")
    assert parsed[0]["intensity"] == 330
    assert normalize_observation(parsed[0])["metadata"]["frp"] == "17.2"

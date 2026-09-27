import pytest
from app.ml.classifier import classify_with_fallback, model_status
from app.ml.weak_classifier import predict_weak, weak_model_status

def test_anomaly_model_status():
    status = model_status()
    assert isinstance(status, dict)
    assert "status" in status

def test_weak_model_status():
    status = weak_model_status()
    assert isinstance(status, dict)

def test_anomaly_model_fallback_with_demo():
    # If the real model can't be loaded, the system should correctly fall back
    # or return a valid status in demo mode.
    status = model_status(demo=True)
    assert status["status"] in ["ACTIVE", "UNAVAILABLE", "FALLBACK", "RULE_BASED_FALLBACK"]

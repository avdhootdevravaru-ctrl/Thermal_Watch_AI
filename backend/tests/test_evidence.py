import pytest
import os
import tempfile
import json
import copy
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.evidence import (
    evidence_package,
    verify_evidence,
    anchor_local,
    verify_chain,
    _hash,
)
from app.config import settings

@pytest.fixture(autouse=True)
def isolated_chain(tmp_path, monkeypatch):
    monkeypatch.setattr("app.evidence._chain_path", lambda: tmp_path / "local.jsonl")
    monkeypatch.setattr(settings, "BLOCKCHAIN_ENABLED", False)


@pytest.mark.parametrize("mutation", ["modified", "deleted_middle", "deleted_tail", "deleted_all", "reordered", "previous_hash"])
def test_chain_detects_tampering(sample_event, mutation):
    from app.evidence import _chain_path
    sample_event["data_mode"] = "DEMO DATA"
    for event_id in (1, 2, 3):
        sample_event["id"] = event_id
        anchor_local(evidence_package(sample_event))
    assert verify_chain()["valid"]
    path = _chain_path()
    receipts = [json.loads(line) for line in path.read_text().splitlines()]
    if mutation == "modified":
        receipts[0]["event_id"] = 99
    elif mutation == "deleted_middle":
        del receipts[1]
    elif mutation == "deleted_tail":
        receipts.pop()
    elif mutation == "deleted_all":
        receipts.clear()
    elif mutation == "reordered":
        receipts.reverse()
    else:
        receipts[1]["previous_sha256"] = "f" * 64
    path.write_text("\n".join(json.dumps(row) for row in receipts), encoding="utf-8")
    assert not verify_chain()["valid"]
    with pytest.raises(ValueError, match="chain is invalid"):
        anchor_local(evidence_package(sample_event))


def test_observation_order_and_modified_package(sample_event):
    sample_event["data_mode"] = "DEMO DATA"
    package = evidence_package(sample_event)
    sample_event["observations"].reverse()
    assert evidence_package(sample_event)["sha256"] == package["sha256"]
    anchor_local(package)
    altered = copy.deepcopy(package)
    altered["payload"]["risk"]["score"] += 1
    assert not verify_evidence(altered)["local_anchor_valid"]
    with pytest.raises(ValueError, match="digest"):
        anchor_local(altered)

@pytest.fixture
def sample_event():
    class DummyObservation:
        def __init__(self, ts, lat, lon, intensity, conf, source, sensor, meta):
            self.timestamp = ts
            self.latitude = lat
            self.longitude = lon
            self.intensity = intensity
            self.confidence = conf
            self.source = source
            self.sensor = sensor
            self.metadata_json = meta

    now = datetime.now(timezone.utc)
    obs = [
        DummyObservation(now, 22.8, 86.2, 350.0, 80, "FIRMS", "VIIRS", {"frp": 10.0}),
        DummyObservation(now, 22.9, 86.3, 360.0, 90, "FIRMS", "VIIRS", {"frp": 12.0}),
    ]
    
    return {
        "id": 9001,
        "data_mode": "FIRMS SNAPSHOT",
        "start_time": now,
        "end_time": now,
        "persistence": {"trend": "INCREASING"},
        "risk": {"score": 85, "severity": "HIGH", "factors": ["High intensity"]},
        "classification": {
            "classification": "INDUSTRIAL",
            "model_status": "ACTIVE",
            "model_version": "v1.0",
            "anomaly_score": 0.8,
            "methodology": "ML"
        },
        "observations": obs,
    }


def test_evidence_package_deterministic(sample_event):
    with patch("app.ml.weak_classifier.predict_weak") as mock_predict_weak:
        mock_predict_weak.return_value = {
            "prediction": "INDUSTRIAL",
            "model_status": "ACTIVE",
            "model_version": "1.0",
            "uncalibrated_model_scores": {},
            "feature_values": {},
            "top_contributing_features": [],
            "model_provenance": "test"
        }
        
        pkg1 = evidence_package(sample_event)
        pkg2 = evidence_package(sample_event)
        
        assert pkg1["sha256"] == pkg2["sha256"]
        assert pkg1["evidence_id"] == pkg2["evidence_id"]


def test_verify_evidence_success(sample_event):
    with patch("app.ml.weak_classifier.predict_weak") as mock_predict_weak, patch("app.evidence.verify_chain") as mock_vc:
        mock_predict_weak.return_value = {"prediction": "INDUSTRIAL", "model_status": "ACTIVE", "model_version": "1.0", "uncalibrated_model_scores": {}, "feature_values": {}, "top_contributing_features": [], "model_provenance": "test"}
        mock_vc.return_value = {"valid": False, "receipt_count": 0}
        
        pkg = evidence_package(sample_event)
        result = verify_evidence(pkg)
        
        assert result["content_hash_valid"] is True
        assert result["evidence_id"] == pkg["evidence_id"]


def test_verify_evidence_tampered(sample_event):
    with patch("app.ml.weak_classifier.predict_weak") as mock_predict_weak, patch("app.evidence.verify_chain") as mock_vc:
        mock_predict_weak.return_value = {"prediction": "INDUSTRIAL", "model_status": "ACTIVE", "model_version": "1.0", "uncalibrated_model_scores": {}, "feature_values": {}, "top_contributing_features": [], "model_provenance": "test"}
        mock_vc.return_value = {"valid": False, "receipt_count": 0}
        
        pkg = evidence_package(sample_event)
        # Tamper payload
        pkg["payload"]["event_id"] = 9999
        
        result = verify_evidence(pkg)
        assert result["content_hash_valid"] is False


def test_anchor_local_and_verify_chain(sample_event):
    with patch("app.ml.weak_classifier.predict_weak") as mock_predict_weak, tempfile.TemporaryDirectory() as tmpdir:
        mock_predict_weak.return_value = {"prediction": "INDUSTRIAL", "model_status": "ACTIVE", "model_version": "1.0", "uncalibrated_model_scores": {}, "feature_values": {}, "top_contributing_features": [], "model_provenance": "test"}
        
        pkg = evidence_package(sample_event)
        
        chain_path = os.path.join(tmpdir, "evidence_local_chain.jsonl")
        
        with patch("app.evidence._chain_path") as mock_chain_path:
            mock_chain_path.return_value = MagicMock()
            mock_chain_path.return_value.is_file.return_value = False
            
            # Since _chain_path returns a pathlib.Path, let's mock it properly
            from pathlib import Path
            mock_chain_path.return_value = Path(chain_path)
            
            # Initial chain should be valid (empty)
            chain_status = verify_chain()
            assert chain_status["valid"] is True
            assert chain_status["receipt_count"] == 0
            
            # Anchor local
            receipt = anchor_local(pkg)
            assert receipt["evidence_id"] == pkg["evidence_id"]
            assert receipt["sequence"] == 1
            
            # Verify chain after anchor
            chain_status2 = verify_chain()
            assert chain_status2["valid"] is True
            assert chain_status2["receipt_count"] == 1
            
            # Verify evidence sees the anchor
            verification = verify_evidence(pkg)
            assert verification["local_anchor_present"] is True
            assert verification["local_anchor_valid"] is True
            assert verification["local_chain_valid"] is True

"""Checks for real-feed validation, physical clustering and evidence integrity."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.config import settings
from app.evidence import anchor_local, evidence_package, verify_chain, verify_evidence
from app.ingestion.validation import validate_firms_csv
from app.processing.clustering import cluster_observations
from app.utils.logging import redact_secrets


def test_validator_keeps_missing_optional_values_and_rejects_invalid_rows():
    csv = ("latitude,longitude,acq_date,acq_time,bright_ti4,frp,confidence\n"
           "20,75,2026-09-26,145,330,4,h\n"
           "20,75,2026-09-26,145,330,4,h\n"
           "NaN,75,2026-09-26,145,330,4,h\n"
           "21,76,2026-09-26,1610,,,-\n"
           "21,77,2026-09-26,9999,320,4,h\n")
    accepted, report = validate_firms_csv(csv, source="VIIRS_NOAA20_NRT")
    assert report.records_received == 5
    assert report.records_accepted == 2
    assert report.records_rejected == 3
    assert report.duplicates_removed == report.invalid_coordinates == report.invalid_timestamps == 1
    assert accepted[0]["timestamp"].hour == 1 and accepted[0]["timestamp"].minute == 45
    assert accepted[0]["confidence"] is None
    assert accepted[0]["metadata"]["confidence_category"] == "high"
    assert accepted[1]["intensity"] is None and accepted[1]["metadata"]["frp"] is None


def test_adjacent_grid_cells_still_require_physical_proximity():
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    rows = [{"latitude": 20.0, "longitude": 75.0, "timestamp": now},
            {"latitude": 20.0, "longitude": 75.09, "timestamp": now}]
    clusters = cluster_observations(rows, distance_meters=1500, time_hours=24)
    assert len(clusters) == 2


def test_evidence_hash_and_local_chain_detect_tampering(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FIRMS_SNAPSHOT_PATH", str(tmp_path / "capture.csv"))
    timestamp = datetime(2026, 9, 26, tzinfo=timezone.utc)
    observation = SimpleNamespace(timestamp=timestamp, latitude=20.0, longitude=75.0,
                                  intensity=330.0, confidence=80.0, source="VIIRS_NOAA20_NRT",
                                  sensor="VIIRS", metadata_json={"frp": 4.0})
    event = {"id": 1, "data_mode": "FIRMS SNAPSHOT", "observations": [observation],
             "start_time": timestamp, "end_time": timestamp,
             "persistence": {"active_days": 1},
             "risk": {"score": 20, "severity": "LOW", "factors": []},
             "classification": {"classification": "within_capture_range", "model_status": "UNSUPERVISED_PROTOTYPE"}}
    package = evidence_package(event)
    assert package["sha256"] == evidence_package(event)["sha256"]
    receipt = anchor_local(package)
    assert receipt["on_chain"] is False
    assert verify_evidence(package)["local_anchor_valid"] is True
    observation.intensity = 331.0
    changed = verify_evidence(evidence_package(event))
    assert changed["local_anchor_present"] is True and changed["local_anchor_valid"] is False
    chain_file = tmp_path / "evidence_local_chain.jsonl"
    chain_file.write_text(chain_file.read_text().replace("VIIRS", "MODIS"), encoding="utf-8")
    # The previous replacement may not change a receipt, so alter a linked digest.
    content = chain_file.read_text(encoding="utf-8")
    chain_file.write_text(content.replace(receipt["evidence_sha256"], "0" * 64), encoding="utf-8")
    assert verify_chain()["valid"] is False


def test_firms_path_key_is_redacted_from_http_logs():
    message = "GET https://firms.modaps.eosdis.nasa.gov/api/area/csv/secret-test/VIIRS_NOAA20_NRT/world/1"
    cleaned = redact_secrets(message)
    assert "secret-test" not in cleaned
    assert "/api/area/csv/[REDACTED]/" in cleaned

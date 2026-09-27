"""Source-status and shared FIRMS validation contracts."""

from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.ingestion.capture import capture_firms_to_files
from app.ingestion.validation import validate_firms_csv
from app.main import app


def test_saved_capture_status_reports_actual_counts_and_storage(monkeypatch):
    monkeypatch.setattr("app.db.health.database_status", lambda: {
        "database": "NOT_CONNECTED", "postgis": "UNAVAILABLE", "database_persisted": False,
        "persisted_observations": 0, "persisted_events": 0, "checked_at": "test",
    })
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "FIRMS_SNAPSHOT_PATH", "test-only.csv")
    monkeypatch.setattr("app.snapshot.snapshot_state", lambda: {
        "source": "VIIRS_NOAA20_NRT", "capture_time": "2026-09-27T09:00:00+00:00",
        "events": {1: {}, 2: {}}, "validation": {
            "latest_observation": "2026-09-27T08:00:00+00:00",
            "records_received": 4, "records_accepted": 3, "records_rejected": 1,
            "duplicates_removed": 0, "rejection_reasons": {"INVALID_FRP": 1},
        },
    })
    with TestClient(app) as client:
        response = client.get("/firms/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SAVED_CAPTURE"
        assert data["observation_count"] == 3
        assert data["event_count"] == 2
        assert data["validation_status"] == "VALIDATED"
        assert data["database_persisted"] is False
        assert data["is_live"] is False
        assert client.get("/firms/status", headers={"Origin": "http://localhost:3000"}).headers[
            "access-control-allow-origin"] == "http://localhost:3000"
        assert "access-control-allow-origin" not in client.get(
            "/firms/status", headers={"Origin": "https://untrusted.example"}).headers


def test_optional_measurements_are_validated_without_rejecting_missing_values():
    csv = (
        "latitude,longitude,acq_date,acq_time,bright_ti4,scan,track,frp,confidence\n"
        "21,79,2026-09-27,1200,310,0.5,0.4,1.2,n\n"
        "22,79,2026-09-27,1201,310,-1,0.4,1.2,n\n"
        "23,79,2026-09-27,1202,310,0.5,nan,1.2,n\n"
        "24,79,2026-09-27,1203,310,0.5,0.4,1.2,unverified\n"
        "25,79,2026-09-27,1204,310,,,,\n"
    )
    accepted, report = validate_firms_csv(csv, source="VIIRS_NOAA20_NRT")
    assert len(accepted) == 2
    assert report.rejection_reasons == {
        "INVALID_SCAN": 1, "INVALID_TRACK": 1, "INVALID_CONFIDENCE": 1,
    }
    assert report.missing_values["scan"] == 1
    assert report.missing_values["track"] == 1
    assert report.missing_values["frp"] == 1
    assert report.missing_values["confidence"] == 1


def test_failed_firms_refresh_preserves_last_capture(tmp_path, monkeypatch):
    capture = tmp_path / "firms_latest_raw.csv"
    capture.write_text("existing validated capture", encoding="utf-8")
    monkeypatch.setattr(settings, "FIRMS_MAP_KEY", "test-key")

    def fail_fetch(_self):
        raise ConnectionError("network unavailable")

    monkeypatch.setattr("app.ingestion.firms_client.FirmsClient.fetch_csv", fail_fetch)
    with pytest.raises(ConnectionError):
        capture_firms_to_files(
            source="VIIRS_NOAA20_NRT", area="IND", days=3, path=capture,
        )
    assert capture.read_text(encoding="utf-8") == "existing validated capture"

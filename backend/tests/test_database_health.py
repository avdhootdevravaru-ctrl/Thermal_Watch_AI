import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.config import settings

client = TestClient(app)


@patch("app.api.health.engine.connect")
def test_database_health_snapshot_mode_connected(mock_connect):
    mock_connection = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_connection
    mock_connection.execute.return_value.scalar_one.side_effect = [
        "PostgreSQL 14.0",
        "3.1 USE_GEOS=1",
        100,  # obs_count
        5     # event_count
    ]

    # Temporarily force snapshot mode if not already
    original_snapshot = settings.FIRMS_SNAPSHOT_PATH
    original_demo = settings.DEMO_MODE
    settings.FIRMS_SNAPSHOT_PATH = "data/firms_latest_raw.csv"
    settings.DEMO_MODE = False
    
    try:
        response = client.get("/health/database")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "snapshot_with_db"
        assert data["database"] == "CONNECTED"
        assert data["postgis"] == "AVAILABLE"
        assert "pg_version" in data
        assert "postgis_version" in data
        assert data["persisted_observations"] == 100
        assert data["persisted_events"] == 5
        assert data["data_mode"] == "FIRMS SNAPSHOT"
    finally:
        settings.FIRMS_SNAPSHOT_PATH = original_snapshot
        settings.DEMO_MODE = original_demo


@patch("app.api.health.engine.connect")
def test_database_health_unreachable(mock_connect):
    mock_connect.side_effect = Exception("Connection refused")

    original_snapshot = settings.FIRMS_SNAPSHOT_PATH
    original_demo = settings.DEMO_MODE
    settings.FIRMS_SNAPSHOT_PATH = "data/firms_latest_raw.csv"
    settings.DEMO_MODE = False
    
    try:
        response = client.get("/health/database")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "snapshot"
        assert data["database"] == "NOT_CONNECTED"
        assert data["postgis"] == "UNAVAILABLE"
        assert data["persisted_observations"] == 0
        assert data["persisted_events"] == 0
        assert data["data_mode"] == "FIRMS SNAPSHOT"
        assert "note" in data
    finally:
        settings.FIRMS_SNAPSHOT_PATH = original_snapshot
        settings.DEMO_MODE = original_demo


def test_database_health_includes_all_expected_fields():
    response = client.get("/health/database")
    assert response.status_code == 200
    data = response.json()
    
    expected_fields = [
        "status", "database", "postgis", "database_persisted",
        "persisted_observations", "persisted_events", "data_mode"
    ]
    for field in expected_fields:
        assert field in data

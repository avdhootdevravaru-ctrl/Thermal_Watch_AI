"""Pytest fixtures for ThermalWatch AI tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from app.config import settings


@pytest.fixture(scope="session")
def env_path() -> Generator[Path, None, None]:
    """Path to the .env file used in tests."""
    # Use the backend's .env
    p = Path(__file__).parents[2] / "backend" / ".env"
    yield p


@pytest.fixture(scope="session")
def settings_override(env_path) -> Generator[dict, None, None]:
    """Allow tests to read env vars from the .env file."""

    if env_path.exists():
        with open(env_path) as f:
            content = f.read()
        # Parse simple KEY=VALUE lines
        env_vars: dict = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
        yield env_vars
    else:
        yield {}


@pytest.fixture
def sample_firms_observation():
    """A sample normalized FIRMS observation for testing."""
    from app.ingestion.normalizer import normalize_observation

    # Provide a minimal raw dict
    raw = {
        "date": "20260815",
        "time": "143000",
        "latitude": "-15.3",
        "longitude": "145.7",
        "confidence": "high",
        "brightness_temperature": "320.5",
        "frp": "12.5",
        "satellite": "VIIRS_NOAA20_NRT",
    }

    return normalize_observation(raw)


@pytest.fixture
def sample_observation_dict():
    """A normalized observation dict with all required fields."""
    return {
        "latitude": -15.3,
        "longitude": 145.7,
        "timestamp": "2026-08-15T14:30:00+00:00",
        "intensity": 320.5,
        "confidence": 85.0,
        "source": "VIIRS_NOAA20_NRT",
        "sensor": "VIIRS",
        "metadata": {"frp": "12.5", "daynight": "day"},
    }


@pytest.fixture
def sample_observation():
    """A minimal ORM-compatible observation dict."""
    return {
        "latitude": -15.3,
        "longitude": 145.7,
        "timestamp": "2026-08-15T14:30:00+00:00",
        "intensity": 320.5,
        "confidence": 85.0,
        "source": "VIIRS_NOAA20_NRT",
    }


@pytest.fixture
def clustered_event():
    """A sample clustering event result."""
    from datetime import datetime

    return {
        "centroid_lat": -15.3,
        "centroid_lon": 145.7,
        "start_time": datetime(2026, 8, 15, 10, 0, 0),
        "end_time": datetime(2026, 8, 18, 18, 0, 0),
        "observation_count": 8,
        "persistence_score": 8.0,
    }


@pytest.fixture
def sample_persistence_metrics():
    """Persistence metrics for testing."""
    return {
        "total_detections": 8,
        "active_days": 4,
        "persistence_score": 2.0,
        "average_intensity": 315.0,
        "intensity_variance": 15.0,
        "spatial_stability": 0.01,
        "first_detection": "2026-08-13",
        "last_detection": "2026-08-16",
        "trend": "STABLE",
        "persistence_type": "CONFIRMED",
    }
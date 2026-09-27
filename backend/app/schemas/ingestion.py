"""Pydantic schemas for the ingestion API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class IngestionRunRequest(BaseModel):
    """Optional request body for POST /ingestion/firms/run."""
    area: Optional[str] = Field(None, description="Override FIRMS area: world or west,south,east,north (legacy IND maps to India bounding box)")
    days: Optional[int] = Field(None, ge=1, le=5, description="Override look-back days (1–5)")
    satellite: Optional[str] = Field(None, description="Override satellite (e.g. VIIRS_NOAA20_NRT)")


class IngestionResult(BaseModel):
    """Result of a FIRMS ingestion run."""
    status: str = Field(..., description="'success' | 'partial' | 'failed'")
    observations_fetched: int = Field(..., description="Total raw rows returned by FIRMS")
    observations_stored: int = Field(..., description="Rows successfully written to DB")
    observations_failed: int = Field(default=0, description="Rows that failed validation or DB write")
    events_created: int = Field(default=0, description="New ThermalEvent rows created")
    events_updated: int = Field(default=0, description="Existing events that had new observations attached")
    persistent_sources: int = Field(default=0, description="Events flagged as persistent thermal sources")
    observations_invalid_coordinates: int = Field(default=0, description="Rows rejected for out-of-range lat/lon")
    observations_missing_critical_fields: int = Field(default=0, description="Rows rejected for missing required fields")
    observations_duplicate: int = Field(default=0, description="Duplicate observations dropped")
    started_at: datetime
    completed_at: datetime
    errors: list[str] = Field(default_factory=list, description="Non-fatal error messages")
    storage_backend: Optional[str] = None
    records_accepted: Optional[int] = None
    records_rejected: Optional[int] = None


class IngestionStatus(BaseModel):
    """Current ingestion state for health/status endpoints."""
    last_run: Optional[datetime] = None
    last_observations_fetched: int = 0
    last_status: Optional[str] = None

"""Pydantic schemas for the ThermalObservation API model."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class ObservationBase(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees (WGS84)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees (WGS84)")
    timestamp: datetime = Field(..., description="UTC timestamp of the satellite detection")
    intensity: Optional[float] = Field(None, description="Brightness temperature in Kelvin")
    confidence: Optional[float] = Field(None, ge=0, le=100, description="Detection confidence score 0–100")
    source: str = Field(..., description="Satellite source (e.g. VIIRS_NOAA20_NRT)")
    sensor: Optional[str] = Field(None, description="Sensor identifier")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional raw data")


class ObservationCreate(ObservationBase):
    pass


class ObservationRead(ObservationBase):
    id: int
    event_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ObservationSummary(BaseModel):
    id: int
    timestamp: datetime
    latitude: float
    longitude: float
    intensity: Optional[float] = None
    confidence: Optional[float] = None
    source: str

    model_config = {"from_attributes": True}

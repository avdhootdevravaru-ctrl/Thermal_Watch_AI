"""Pydantic schemas for the ThermalEvent API model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.observation import ObservationSummary


class ThermalEventStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PERSISTENT = "PERSISTENT"
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"


class ThermalEventBase(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    start_time: datetime
    end_time: Optional[datetime] = None
    observation_count: int = 0
    persistence_score: float = 0.0
    status: ThermalEventStatus = ThermalEventStatus.UNKNOWN


class ThermalEventCreate(ThermalEventBase):
    pass


class ThermalEventRead(ThermalEventBase):
    id: int

    model_config = {"from_attributes": True}


class ThermalEventDetail(ThermalEventRead):
    """Full event detail including observations."""
    observations: List[ObservationSummary] = Field(default_factory=list)
    persistence: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Persistence analysis results")
    profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Thermal DNA profile")
    risk: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Risk assessment")


class ThermalEventList(BaseModel):
    """Paginated list response for events."""
    total: int
    page: int
    page_size: int
    items: List[ThermalEventRead]


class PersistenceMetrics(BaseModel):
    """Metrics returned by the persistence analysis."""
    total_detections: int
    active_days: int
    persistence_score: float
    average_intensity: Optional[float] = None
    intensity_variance: Optional[float] = None
    spatial_stability: Optional[float] = None
    first_detection: Optional[datetime] = None
    last_detection: Optional[datetime] = None
    trend: str = "UNKNOWN"
    persistence_type: str = "UNKNOWN"


class EventHistoryPoint(BaseModel):
    """Single point on an event's historical timeline."""
    timestamp: datetime
    intensity: Optional[float] = None
    confidence: Optional[float] = None
    observation_count: int = 1

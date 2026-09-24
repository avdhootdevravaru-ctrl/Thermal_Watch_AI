"""Pydantic schemas for the map / hotspots API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HotspotMarker(BaseModel):
    """Single hotspot marker for the GIS map.

    Designed to be lightweight (no observation list) so the map stays fast.
    """
    event_id: int
    latitude: float
    longitude: float
    status: str
    observation_count: int
    persistence_score: float
    trend: Optional[str] = None
    risk_score: Optional[float] = None
    risk_severity: Optional[str] = None
    last_detection: Optional[datetime] = None


class MapHotspotsResponse(BaseModel):
    """Response for the GET /map/hotspots endpoint."""
    total: int
    risk_summary: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by severity: {high: N, medium: M, low: K}",
    )
    markers: List[HotspotMarker]


class FacilityMarker(BaseModel):
    """A facility point for the GIS map."""
    id: int
    name: Optional[str] = None
    type: str
    latitude: float
    longitude: float
    osm_id: Optional[str] = None


class NearbyFacilitiesResponse(BaseModel):
    event_id: int
    facilities: List[FacilityMarker]

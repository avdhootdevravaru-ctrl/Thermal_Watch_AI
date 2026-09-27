"""Map / hotspots API endpoints.

GET /map/hotspots
GET /facilities/nearby
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import ThermalEvent, Facility, RiskAssessment
from app.schemas.map import MapHotspotsResponse, HotspotMarker, NearbyFacilitiesResponse, FacilityMarker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/hotspots", response_model=MapHotspotsResponse)
async def get_map_hotspots(
    risk_severity: Optional[str] = Query(None, description="Filter by severity: high, medium, low"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> MapHotspotsResponse:
    """Get thermal hotspot data formatted for the GIS map.

    Returns a list of markers with risk classification and metadata.
    """
    # Start with a base query that joins ThermalEvent with RiskAssessment if available
    events_query = db.query(ThermalEvent)

    # Always filter to India geographic bounds (safety net for legacy data)
    events_query = events_query.filter(
        ThermalEvent.latitude >= 6.5,
        ThermalEvent.latitude <= 35.5,
        ThermalEvent.longitude >= 68.0,
        ThermalEvent.longitude <= 97.5,
    )

    events = events_query.limit(limit).all()

    # Build markers using stored risk assessments where available
    markers = []
    risk_summary = {"high": 0, "medium": 0, "low": 0}

    for event in events:
        # Try to get stored risk assessment first
        risk = db.query(RiskAssessment).filter(RiskAssessment.event_id == event.id).first()

        # Determine risk severity and score
        if risk and risk.severity:
            # Use stored risk assessment
            severity = risk.severity.lower()
            # Normalize severity to high/medium/low
            if severity == "critical" or severity == "high":
                normalized_severity = "high"
            elif severity == "medium":
                normalized_severity = "medium"
            else:
                normalized_severity = "low"

            if risk_severity and normalized_severity != risk_severity.lower():
                continue

            # Get persistence score from risk if available, otherwise compute
            persistence_score = event.persistence_score
            trend = None  # Could be added to RiskAssessment if needed

            # Update risk summary
            risk_summary[normalized_severity] += 1

            # Create marker with stored risk data
            marker = HotspotMarker(
                event_id=event.id,
                latitude=event.latitude,
                longitude=event.longitude,
                status=event.status,
                observation_count=event.observation_count,
                persistence_score=event.persistence_score,
                trend=trend,
                risk_score=risk.score if hasattr(risk, 'score') else event.persistence_score,
                risk_severity=normalized_severity,
                last_detection=event.end_time,
            )
        else:
            # Fallback to rule-based classification if no stored risk
            if event.status == "PERSISTENT" and event.persistence_score >= 5:
                severity = "high"
            elif event.status == "ACTIVE":
                severity = "medium"
            else:
                severity = "low"

            if risk_severity and severity != risk_severity.lower():
                continue

            risk_summary[severity] += 1

            marker = HotspotMarker(
                event_id=event.id,
                latitude=event.latitude,
                longitude=event.longitude,
                status=event.status,
                observation_count=event.observation_count,
                persistence_score=event.persistence_score,
                trend=None,
                risk_score=event.persistence_score,
                risk_severity=severity,
                last_detection=event.end_time,
            )

        markers.append(marker)

    return MapHotspotsResponse(
        total=len(markers),
        risk_summary=risk_summary,
        markers=markers,
    )


@router.get("/facilities/nearby", response_model=NearbyFacilitiesResponse)
async def get_nearby_facilities(
    event_id: int = Query(..., description="Thermal event ID"),
    radius_km: float = Query(5.0, ge=0.1, le=100.0, description="Search radius in km"),
    db: Session = Depends(get_db),
) -> NearbyFacilitiesResponse:
    """Find facilities near a thermal event using PostGIS spatial queries.

    Uses ST_DWithin to find facilities within `radius_km` of the event centroid.
    """
    event = db.query(ThermalEvent).filter(ThermalEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # PostGIS spatial query: ST_DWithin(geom1, geom2, distance_meters)
    radius_meters = radius_km * 1000.0

    facilities = db.query(Facility).filter(
        Facility.geometry.is_not(None),
        # ST_DWithin returns true if the geometries are within the given distance
        # We use the raw SQL expression for PostGIS compatibility
        Facility.geometry.ST_DWithin(
            db.query(ThermalEvent.geometry).filter(ThermalEvent.id == event_id).subquery(),
            radius_meters,
        )
    ).all()

    facility_markers = [
        FacilityMarker(
            id=f.id,
            name=f.name,
            type=f.type,
            latitude=f.latitude,
            longitude=f.longitude,
            osm_id=f.osm_id,
        )
        for f in facilities
    ]

    return NearbyFacilitiesResponse(
        event_id=event_id,
        facilities=facility_markers,
    )

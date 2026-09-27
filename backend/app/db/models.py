"""SQLAlchemy ORM models for the ThermalWatch database.

All geometry columns use PostGIS via GeoAlchemy2.
The SRID used is 4326 (WGS84 — what NASA FIRMS and OSM use).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geometry
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ObservationSource(str, enum.Enum):
    """Enumerated source values for thermal observations."""
    VIIRS_NOAA20_NRT = "VIIRS_NOAA20_NRT"
    VIIRS_SNPP_NRT = "VIIRS_SNPP_NRT"
    MODIS_NRT = "MODIS_NRT"
    MODIS_MOD14ML = "MODIS_MOD14ML"
    MODIS_MCD14ML = "MODIS_MCD14ML"
    OTHER = "OTHER"


class ThermalObservation(Base):
    """A single thermal anomaly detection from a satellite pass.

    Mirrors the NASA FIRMS CSV schema but normalized into a typed row.
    """

    __tablename__ = "thermal_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Core spatial-temporal fields
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Thermal properties
    intensity: Mapped[Optional[float]] = mapped_column(Float)        # Brightness temperature (K)
    confidence: Mapped[Optional[float]] = mapped_column(Float)        # 0–100 (MODIS) or low/med/high

    # Source / provenance
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    sensor: Mapped[Optional[str]] = mapped_column(String(50))

    # Flexible metadata (original CSV row, extra columns)
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSONB, name="metadata")

    # Geometry
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, dimension=2),
        nullable=False,
    )

    # FK to the thermal event this observation belongs to (nullable until clustering assigns it)
    event_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("thermal_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event: Mapped[Optional["ThermalEvent"]] = relationship("ThermalEvent", back_populates="observations")

    __table_args__ = (
        Index("idx_thermal_obs_timestamp", "timestamp"),
        Index("idx_thermal_obs_geometry", "geometry", postgresql_using="gist"),
        Index(
            "idx_thermal_obs_source_time",
            "source", "timestamp",
        ),
    )


class ThermalEventStatus(str, enum.Enum):
    """Lifecycle state of a thermal event."""
    ACTIVE = "ACTIVE"           # Ongoing detections
    PERSISTENT = "PERSISTENT"   # Confirmed recurring source
    RESOLVED = "RESOLVED"       # Activity has ceased
    UNKNOWN = "UNKNOWN"


class ThermalEvent(Base):
    """A cluster of thermal observations that are spatially and temporally close.

    Created by the DBSCAN-based clustering algorithm. A single event aggregates
    multiple individual satellite detections that are believed to originate
    from the same physical source.
    """

    __tablename__ = "thermal_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Centroid (representative location)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Temporal bounds
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Summary metrics
    observation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    persistence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ThermalEventStatus.ACTIVE.value
    )

    # Geometry: bounding polygon of all constituent observations
    geometry: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326),
    )

    # Relationships
    observations: Mapped[list["ThermalObservation"]] = relationship(
        "ThermalObservation",
        back_populates="event",
        lazy="select",
    )
    profile: Mapped[Optional["ThermalProfile"]] = relationship(
        "ThermalProfile",
        back_populates="event",
        uselist=False,
    )
    risk: Mapped[Optional["RiskAssessment"]] = relationship(
        "RiskAssessment",
        back_populates="event",
        uselist=False,
    )

    __table_args__ = (
        Index("idx_thermal_event_time", "start_time", "end_time"),
        Index("idx_thermal_event_geom", "geometry", postgresql_using="gist"),
        Index("idx_thermal_event_status", "status"),
    )


class FacilityType(str, enum.Enum):
    """Simplified facility classification."""
    POWER_PLANT = "power_plant"
    FACTORY = "factory"
    REFINERY = "refinery"
    LANDMARK = "landmark"
    OTHER = "other"


class Facility(Base):
    """An industrial facility or geographic feature from OpenStreetMap.

    Populated lazily via OSM Overpass queries for areas near thermal events.
    """

    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    osm_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50), nullable=False, default=FacilityType.OTHER.value)

    # Location / geometry
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    geometry: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, dimension=2),
    )

    # Flexible OSM metadata
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSONB, name="metadata")

    __table_args__ = (
        Index("idx_facility_geom", "geometry", postgresql_using="gist"),
        Index("idx_facility_osm", "osm_id"),
    )


class ThermalProfile(Base):
    """Behavioural fingerprint ("Thermal DNA") of a thermal event.

    Computed after an event has accumulated enough detections. This table is
    populated in later milestones, but the schema is defined here so the event
    relationship works from day one.
    """

    __tablename__ = "thermal_profiles"

    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("thermal_events.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # --- TEMPORAL FEATURES ---
    first_detection: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_detection: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    active_days: Mapped[Optional[int]] = mapped_column(Integer)
    duration_hours: Mapped[Optional[float]] = mapped_column(Float)
    detection_frequency: Mapped[Optional[float]] = mapped_column(Float)  # detections per active day
    recurrence: Mapped[Optional[int]] = mapped_column(Integer)  # number of distinct detection events
    temporal_pattern: Mapped[Optional[str]] = mapped_column(String(50))
    trend: Mapped[Optional[str]] = mapped_column(String(50))

    # --- INTENSITY FEATURES ---
    average_intensity: Mapped[Optional[float]] = mapped_column(Float)
    max_intensity: Mapped[Optional[float]] = mapped_column(Float)
    min_intensity: Mapped[Optional[float]] = mapped_column(Float)
    intensity_variance: Mapped[Optional[float]] = mapped_column(Float)
    intensity_trend: Mapped[Optional[str]] = mapped_column(String(50))
    frp_mean: Mapped[Optional[float]] = mapped_column(Float)
    frp_max: Mapped[Optional[float]] = mapped_column(Float)

    # --- SPATIAL FEATURES ---
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float)
    spatial_spread: Mapped[Optional[float]] = mapped_column(Float)  # bounding box area
    spatial_variance: Mapped[Optional[float]] = mapped_column(Float)
    spatial_stability: Mapped[Optional[float]] = mapped_column(Float)
    distinct_detections: Mapped[Optional[int]] = mapped_column(Integer)

    # --- PERSISTENCE FEATURES ---
    persistence_score: Mapped[Optional[float]] = mapped_column(Float)
    consecutive_active_days: Mapped[Optional[int]] = mapped_column(Integer)
    persistence_type: Mapped[Optional[str]] = mapped_column(String(50))

    # --- DATA QUALITY ---
    observation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_distribution: Mapped[Optional[Any]] = mapped_column(JSONB)
    source_distribution: Mapped[Optional[Any]] = mapped_column(JSONB)
    data_completeness: Mapped[Optional[float]] = mapped_column(Float)  # 0-1 fraction of non-null features

    # --- BASELINE / COMPARISON ---
    baseline: Mapped[Optional[Any]] = mapped_column(JSONB)
    baseline_status: Mapped[Optional[str]] = mapped_column(String(50))
    baseline_deviation: Mapped[Optional[Any]] = mapped_column(JSONB)

    # --- LEGACY FIELDS (backward compat) ---
    frequency: Mapped[float] = mapped_column(Float, default=0.0)

    event: Mapped[Optional["ThermalEvent"]] = relationship(
        back_populates="profile",
    )


class Classification(str, enum.Enum):
    """Possible classification labels for thermal events."""
    INDUSTRIAL_THERMAL_SOURCE = "industrial_thermal_source"
    PERSISTENT_THERMAL_SOURCE = "persistent_thermal_source"
    INDUSTRIAL_FIRE = "industrial_fire"
    AGRICULTURAL_BURNING = "agricultural_burning"
    NATURAL_SOURCE = "natural_thermal_source"
    TEMPORARY_EVENT = "temporary_thermal_event"
    UNKNOWN = "unknown"


class Prediction(Base):
    """Machine-learning prediction for a thermal event."""

    __tablename__ = "predictions"

    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("thermal_events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    probabilities: Mapped[Optional[Any]] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False,
    )

    event: Mapped[Optional["ThermalEvent"]] = relationship(
        "ThermalEvent",
    )


class RiskLevel(str, enum.Enum):
    """Risk severity tiers."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskAssessment(Base):
    """Risk score and supporting explanation for a thermal event."""

    __tablename__ = "risk_assessments"

    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("thermal_events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)   # 0–100
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    contributing_factors: Mapped[Optional[Any]] = mapped_column(JSONB)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False,
    )

    event: Mapped[Optional["ThermalEvent"]] = relationship(
        back_populates="risk",
    )

"""Custom exception classes for ThermalWatch AI."""

from __future__ import annotations


class ThermalWatchError(Exception):
    """Base exception for ThermalWatch AI."""
    pass


class IngestionError(ThermalWatchError):
    """Raised when FIRMS data ingestion fails."""
    pass


class ClusteringError(ThermalWatchError):
    """Raised when event clustering fails."""
    pass


class PersistenceError(ThermalWatchError):
    """Raised when persistent-source detection fails."""
    pass


class ValidationError(ThermalWatchError):
    """Raised when data validation fails."""
    pass


class DatabaseError(ThermalWatchError):
    """Raised when database operations fail."""
    pass


class ConfigurationError(ThermalWatchError):
    """Raised when configuration is invalid or missing."""
    pass


class APIError(ThermalWatchError):
    """Raised when an external API call fails."""
    pass
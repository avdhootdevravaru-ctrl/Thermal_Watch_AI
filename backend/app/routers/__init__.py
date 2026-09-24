"""FastAPI routers aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.api.events import router as events_router
from app.api.map import router as map_router
from app.api.history import router as history_router

__all__ = ["health_router", "ingestion_router", "events_router", "map_router", "history_router"]
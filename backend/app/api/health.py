"""Health check endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> dict:
    """Return a simple health status.

    This is a lightweight endpoint that does not touch the database.
    A full DB check would be added in production.
    """
    return {
        "status": "ok",
        "service": "ThermalWatch AI",
        "version": "0.1.0",
    }
"""ThermalWatch AI — FastAPI Application Entry Point.

Run with: uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.routers import (
    health_router,
    ingestion_router,
    events_router,
    map_router,
    history_router,
)
from app.utils.logging import setup_logging

# --- Logging setup ---
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle.

    Use this for:
      - Database connection pool initialization
      - Background task startup
      - Cache warm-up
    """
    logger.info("ThermalWatch AI starting up...")
    # Startup code here
    yield
    # Shutdown code here
    logger.info("ThermalWatch AI shutting down...")


app = FastAPI(
    title="ThermalWatch AI API",
    description=(
        "AI-Based Detection and Classification of Industrial Fires and "
        "Persistent Thermal Sources Using NASA FIRMS, OSM & Satellite Data.\n\n"
        "SIH 2026 Problem Statement: SIH26162\n"
        "Sponsor: National Technical Research Organisation (NTRO)"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.exception_handler(OperationalError)
async def database_unavailable(_request, exc: OperationalError):
    logger.error("Database request failed: %s", exc.orig)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable. Start PostgreSQL/PostGIS or enable explicit demo mode."},
    )

# --- CORS (adjust for production) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, set specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(health_router)
if settings.DEMO_MODE or settings.FIRMS_SNAPSHOT_PATH:
    from app.demo import router as demo_router
    app.include_router(demo_router)
else:
    app.include_router(ingestion_router)
    app.include_router(events_router)
    app.include_router(map_router)
    app.include_router(history_router)


# --- Root endpoint ---
@app.get("/")
async def root() -> dict:
    return {
        "service": "ThermalWatch AI",
        "version": "0.1.0",
        "description": "Geospatial intelligence for industrial fire detection",
        "docs": "/docs",
        "health": "/health",
        "data_mode": "DEMO DATA" if settings.DEMO_MODE else
        "FIRMS SNAPSHOT" if settings.FIRMS_SNAPSHOT_PATH else "LIVE MODE",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.APP_ENV == "development",
    )

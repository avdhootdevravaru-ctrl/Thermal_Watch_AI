"""ThermalWatch AI — FastAPI Application Entry Point.

Run with: uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import health_router, ingestion_router, events_router, map_router
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
app.include_router(ingestion_router)  # router already has prefix="/ingestion"
app.include_router(events_router)  # router already has prefix="/thermal-events"
app.include_router(map_router)  # router already has prefix="/map"
app.include_router(history_router)  # router already has prefix="/history"


# --- Root endpoint ---
@app.get("/")
async def root() -> dict:
    return {
        "service": "ThermalWatch AI",
        "version": "0.1.0",
        "description": "Geospatial intelligence for industrial fire detection",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.APP_ENV == "development",
    )
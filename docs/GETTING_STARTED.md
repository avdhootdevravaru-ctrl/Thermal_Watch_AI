# ThermalWatch AI — Getting Started Guide

This document covers the PostgreSQL/PostGIS deployment path. For the working
real FIRMS local prototype when PostGIS is unavailable, follow the
[repository quick start](../README.md#current-real-firms-prototype-windows).
That path retains actual NASA CSV data locally, reports its capture time and
validation counts, and labels database persistence as unavailable.

## Prerequisites

1. **Python 3.11+**
2. **PostgreSQL 14+** with **PostGIS 3.x** extension
3. **Git**
4. **Node.js 18+** and **npm**
5. A **NASA FIRMS MAP_KEY** (free registration at <https://firms.modaps.eosdis.nasa.gov/api/map_key/>)

## Quick Start

### 1. Clone the repository

```bash
git clone <repository-url>
cd thermalwatch
```

### 2. Create virtual environments

```bash
# Backend
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt

# Frontend (in a separate terminal)
cd ../frontend
npm install
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values:
#   DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/thermalwatch
#   FIRMS_MAP_KEY=your_firms_map_key_here
#   FIRMS_AREA=68,6.5,97.5,35.5  # India bounding box for Area API
#   FIRMS_DAYS=5        # Area API maximum per request
```

### 4. Initialize the database

```bash
# Create the database first (if it doesn't exist):
createdb thermalwatch   # Linux/macOS
# OR use pgAdmin

# Enable PostGIS extension:
psql -d thermalwatch -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Run the schema migrations:
python -m app.db.init_db
```

Expected output:

```
INFO:__main__:Connecting to database: postgresql+psycopg2://****@localhost:5432/thermalwatch
INFO:__main__:Schema created successfully. Tables: ['thermal_observations', 'thermal_events', 'thermal_profiles', ...]
```

### 5. Run the API server

```bash
uvicorn app.main:app --reload --port 8000
```

The server will be available at:
- **API**: <http://localhost:8000>
- **Interactive docs (Swagger UI)**: <http://localhost:8000/docs>
- **Alternative docs (ReDoc)**: <http://localhost:8000/redoc>
- **Health check**: <http://localhost:8000/health>

### 6. Run the frontend

```bash
cd frontend
npm run dev
```

Open <http://localhost:3000> for the interactive GIS dashboard.

### 7. Trigger a FIRMS ingestion run

```bash
curl -X POST "http://localhost:8000/ingestion/firms/run"
```

Or via the Swagger UI at <http://localhost:8000/docs>.

### 8. Explore the data

After ingestion completes, check:
- **Thermal events**: <http://localhost:8000/thermal-events>
- **Map hotspots**: <http://localhost:8000/map/hotspots>
- **Event details**: <http://localhost:8000/thermal-events/1> (replace `1` with an actual ID)
- **Historical intelligence**: The dashboard sidebar shows a **Historical Intelligence** panel with total observations, total events, data status, duplicate observations, orphan events, observation mismatches, recurring locations, active locations, and persistent sources.
- **Thermal DNA profile**: Navigate to any event detail page to see the **Thermal DNA Profile** section with Temporal, Intensity, Spatial, Persistence, and Data Quality features.

## Historical Intelligence (Task Group 1)

The Historical Intelligence foundation consists of four distinct concepts that must be kept separate:

1. **Thermal DNA** = What the thermal behavior looks like (frequency, active days, duration, intensity, variance, temporal trend, spatial spread/stability, recurrence/persistence, confidence/source info)
2. **Historical baseline** = What is normal for that location
3. **Baseline deviation** = How current behavior differs from normal
4. **Data quality monitoring** = Comprehensive reports distinguishing genuine data issues from processing artifacts

### Thermal DNA

Thermal DNA is computed by `app/processing/thermal_profile.py` from genuine database observations. It uses explicit NULL/UNKNOWN/INSUFFICIENT_DATA semantics rather than fabricated values. Minimum data requirements per feature category are documented in `MIN_OBSERVATIONS`:

| Feature category | Minimum observations |
|------------------|---------------------|
| Temporal features | 2 |
| Intensity features | 1 |
| Spatial features | 2 |
| Persistence features | 2 |
| Data quality | 1 |

If an event has insufficient observations, the affected features are returned as `INSUFFICIENT_DATA` rather than fabricated values.

### Baseline methodology

Location-specific baselines are computed by `compute_baseline()` using historical observations within a configurable radius (default 50km). Baseline status is determined by data sufficiency:

| Status | Meaning |
|--------|---------|
| `SUFFICIENT_HISTORY` | 5+ observations within radius |
| `INSUFFICIENT_HISTORY` | 2-4 observations within radius |
| `NO_HISTORY` | 0-1 observations within radius |

The baseline comparison is a **statistical baseline comparison (not ML anomaly detection)**. If insufficient history exists, the system marks the result as `INSUFFICIENT_HISTORY` and does not fabricate data, Thermal DNA, or baselines.

### Current dataset limitations

The current dataset has limited historical depth. The system handles this honestly by marking results as `INSUFFICIENT_HISTORY` when minimum data requirements are not met.

## Development

### Running tests

```bash
pytest -v
```

### Code formatting

```bash
# Install dev tools
pip install black isort ruff

# Format code
black .
isort .

# Lint
ruff check .
```

### Frontend type-checking and build

```bash
cd frontend
npx tsc --noEmit
npm run build
```

## Project Structure

```
thermalwatch/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Pydantic settings (env vars)
│   │   ├── db/
│   │   │   ├── base.py          # SQLAlchemy engine + session
│   │   │   ├── models.py        # ORM models (PostGIS-backed)
│   │   │   └── init_db.py       # Schema bootstrap
│   │   ├── ingestion/
│   │   │   ├── firms_client.py  # NASA FIRMS HTTP client
│   │   │   └── normalizer.py    # FIRMS → internal schema
│   │   ├── processing/
│   │   │   ├── clustering.py    # Spatial-temporal event clustering (DBSCAN)
│   │   │   ├── persistence.py   # Persistent-source detection
│   │   │   ├── thermal_profile.py  # Thermal DNA / historical intelligence
│   │   │   └── quality.py       # Data quality monitoring
│   │   ├── api/
│   │   │   ├── health.py        # /health endpoint
│   │   │   ├── ingestion.py     # FIRMS ingestion endpoint
│   │   │   ├── events.py        # Thermal events CRUD
│   │   │   ├── map.py           # Map/hotspots endpoints
│   │   │   └── history.py       # Historical intelligence endpoints
│   │   ├── schemas/             # Pydantic API models
│   │   ├── utils/               # Logging, config, helpers
│   │   └── routers/             # Router aggregation
│   ├── tests/                   # Pytest test suite
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/                    # React + TypeScript (Vite)
├── docs/                        # Architecture & design notes
├── PROJECT_STATUS.md            # Current development status
└── README.md
```

## Environment Variables

All configuration lives in `.env` (never commit real secrets!):

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENV` | Environment (`development`/`production`) | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `API_HOST` | Bind host | `0.0.0.0` |
| `API_PORT` | Bind port | 8000 |
| `DATABASE_URL` | PostgreSQL+PostGIS connection string | `postgresql+psycopg2://thermalwatch:thermalwatch@localhost:5432/thermalwatch` |
| `FIRMS_MAP_KEY` | NASA FIRMS MAP_KEY (required) | *(your key)* |
| `FIRMS_SATELLITE` | Sensor (`VIIRS_NOAA20_NRT`, `MODIS_NRT`, etc.) | `VIIRS_NOAA20_NRT` |
| `FIRMS_AREA` | Area API bounding box (`west,south,east,north`) or `world`; legacy `IND` maps to India box | `world` |
| `FIRMS_DAYS` | Look-back days (1–5) | `1` |
| `CLUSTER_DISTANCE_METERS` | Spatial clustering radius | `1000.0` |
| `CLUSTER_TIME_HOURS` | Temporal clustering window | `72.0` |
| `PERSISTENCE_MIN_DETECTIONS` | Min detections for persistent source | `3` |

## API Endpoints (Task Group 1 — Historical Intelligence)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/history/data-quality` | Comprehensive historical data quality report |
| GET | `/history/statistics` | Historical thermal statistics |
| GET | `/history/location/{lat}/{lon}/statistics` | Location-specific historical statistics |
| GET | `/history/location/{lat}/{lon}/baseline` | Location-specific historical baseline |
| POST | `/history/location/{lat}/{lon}/compare` | Compare current observations against baseline |
| GET | `/history/event/{event_id}/profile` | Get computed Thermal DNA profile for an event |
| POST | `/history/event/{event_id}/profile` | Compute and persist Thermal DNA profile for an event |

## Known Legacy Issues

- **94 legacy orphan events**: These are OLD events from before the ingestion integrity phase. They remain untouched and are preserved exactly as they were.
- **665 legacy UNKNOWN sources**: These are OLD observations from before the source attribution phase. They remain untouched and are preserved exactly as they were.
- **FastAPI/Starlette version incompatibility**: 4 pre-existing test failures in `test_data_processing.py` due to `Router.__init__() got an unexpected keyword argument 'on_startup'`. This is unrelated to Task Group 1 and does not affect the historical intelligence functionality.

## Out of Scope (Do Not Implement)

- ML training, supervised classification, ML anomaly detection
- Replacement of the risk engine
- Synthetic labels/data
- Frontend redesign (only integrate historical intelligence into existing UI)
- Geographic search, PDF reports, database rebuild
- Deleting the 94 legacy orphan events
- Rewriting the 665 historical UNKNOWN sources without evidence

## License

Developed for SIH 2026. Internal NTRO / academic use.

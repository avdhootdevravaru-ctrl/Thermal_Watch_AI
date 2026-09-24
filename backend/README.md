# ThermalWatch AI — Backend

FastAPI service that ingests NASA FIRMS thermal observations, normalizes them into
a PostGIS-backed schema, and groups them into persistent thermal events.

## Project layout

```
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Pydantic settings (env vars)
│   ├── db/
│   │   ├── base.py          # SQLAlchemy engine + session
│   │   ├── models.py        # ORM models
│   │   └── init_db.py       # Schema bootstrap
│   ├── ingestion/
│   │   ├── firms_client.py  # NASA FIRMS HTTP client
│   │   └── normalizer.py    # FIRMS → internal schema
│   ├── processing/
│   │   ├── clustering.py    # Spatial-temporal event clustering
│   │   └── persistence.py   # Persistent-source detection
│   ├── api/
│   │   ├── health.py
│   │   ├── ingestion.py
│   │   └── events.py
│   ├── schemas/             # Pydantic API models
│   ├── routers/             # FastAPI routers
│   └── utils/
│       ├── logging.py
│       └── errors.py
├── tests/
└── requirements.txt
```

## Setup

See top-level [README.md](../README.md) for prerequisites. Backend-specific steps:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set DATABASE_URL and FIRMS_MAP_KEY
python -m app.db.init_db
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
pytest -v
```

## Pipeline flow

```
NASA FIRMS API (CSV)
       │
       ▼
firms_client.fetch()        ← httpx + tenacity retries
       │
       ▼
normalizer.to_observations()← parse CSV, validate, map columns
       │
       ▼
ingestion.ingest()          ← upsert ThermalObservation rows
       │
       ▼
clustering.cluster_observations()
       │  DBSCAN over (lat, lon, time) → ThermalEvent
       ▼
persistence.detect_persistent_sources()
       │  count detections / active days per event
       ▼
SQLAlchemy / PostGIS
       │
       ▼
FastAPI → JSON
```

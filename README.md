# ThermalWatch AI

AI-Based Detection and Classification of Industrial Fires and Persistent Thermal Sources
**SIH 2026 — Problem Statement SIH26162** | Sponsor: National Technical Research Organisation (NTRO)

---

## Overview

ThermalWatch AI is a geospatial intelligence platform that combines NASA FIRMS thermal detections, satellite imagery, OpenStreetMap (OSM) data, and historical observations to:

1. Detect and group individual satellite thermal observations into meaningful **thermal events**.
2. Identify **persistent thermal sources** (locations that repeatedly produce detections).
3. Correlate events with nearby industrial facilities and geographic features.
4. Establish a **historical baseline** for each location.
5. Detect **changes from normal behaviour**.
6. Classify events (industrial fire, agricultural burning, natural source, etc.).
7. Generate a **risk score** and **confidence** with an **explainable evidence chain**.
8. Display everything through an **interactive GIS dashboard**.

> **Signature innovations:** *Thermal DNA*, *Change-from-Normal*, *Evidence Chain*.

---

## Repository Structure

This is a **monorepo** with two top-level packages:

```
thermalwatch/
├── backend/                # Python / FastAPI
│   ├── app/
│   │   ├── api/            # FastAPI endpoints (Phase 1 + history)
│   │   ├── db/             # SQLAlchemy + PostGIS connection
│   │   ├── ingestion/      # NASA FIRMS ingestion + normalization
│   │   ├── processing/     # Event clustering, persistence detection, Thermal DNA, quality
│   │   ├── ml/              # ML models (later phases)
│   │   ├── schemas/        # Pydantic models
│   │   ├── utils/          # Logging, config, helpers
│   │   ├── routers/        # Router aggregation
│   │   └── main.py
│   ├── tests/              # Pytest test suite
│   ├── requirements.txt
│   ├── .env.example
│   └── README.md
├── frontend/               # React + TypeScript (Vite)
├── docs/                   # Architecture & design notes
├── PROJECT_STATUS.md       # Current development status
└── README.md
```

---

## Phase 1 (Current Milestone) — Data Foundation + Historical Intelligence

The current milestone focuses on building a clean, runnable data pipeline with historical intelligence:

```
NASA FIRMS
  → ingestion
  → validation
  → PostgreSQL/PostGIS
  → thermal-event clustering
  → persistent-source detection
  → Thermal DNA (historical behavioral fingerprint)
  → statistical baseline comparison
  → REST API
```

Explicitly **out of scope for Phase 1**:

- LLM chatbot
- Computer vision / image segmentation
- Digital twin
- Advanced forecasting
- Mobile app
- Hardware / ESP32
- Microservices
- Fancy frontend animations

---

## Thermal DNA — What It Is (and What It Is Not)

**Thermal DNA** is a behavioral fingerprint of a thermal event computed from genuine database observations. It is NOT machine learning. It uses explicit NULL/UNKNOWN/INSUFFICIENT_DATA semantics rather than fabricated values.

| Feature category | What it measures | Minimum observations |
|------------------|------------------|---------------------|
| Temporal features | First/last detection, active days, duration, detection frequency, recurrence, temporal trend | 2 |
| Intensity features | Mean/max/min brightness temperature, variance, trend, FRP statistics | 1 |
| Spatial features | Centroid, spatial spread, spatial variance, spatial stability, distinct detections | 2 |
| Persistence features | Total detections, active days, consecutive active days, persistence score, persistence type | 2 |
| Data quality | Observation count, completeness, confidence distribution, source distribution | 1 |

If an event has insufficient observations, the affected features are returned as `INSUFFICIENT_DATA` rather than fabricated values.

---

## Baseline Concepts (Keep Separate)

These three concepts are distinct and must not be conflated:

1. **Thermal DNA** = What the thermal behavior looks like (frequency, active days, duration, intensity, variance, temporal trend, spatial spread/stability, recurrence/persistence, confidence/source info)
2. **Historical baseline** = What is normal for that location
3. **Baseline deviation** = How current behavior differs from normal

---

## Quick Start (Backend)

### 1. Prerequisites

- **Python 3.11+**
- **PostgreSQL 14+** with **PostGIS 3.x** extension
- **Node.js 18+** and **npm**
- A **NASA FIRMS API key** (MAP_KEY). Register free at <https://firms.modaps.eosdis.nasa.gov/api/map_key/>

### 2. Database

Create a PostgreSQL database and enable PostGIS:

```sql
CREATE DATABASE thermalwatch;
\c thermalwatch
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 3. Configure environment

```bash
cd backend
cp .env.example .env
# Edit .env with your DB credentials and FIRMS_MAP_KEY
```

### 4. Install dependencies

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 5. Initialize database schema

```bash
python -m app.db.init_db
```

### 6. Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs> for the interactive Swagger UI.

### 7. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> for the interactive GIS dashboard.

### 8. Run tests

```bash
pytest -v
```

---

## API Endpoints (Task Group 1 — Historical Intelligence)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/health` | Health check |
| POST | `/ingestion/firms/run` | Trigger FIRMS data ingestion |
| GET | `/thermal-events` | List detected thermal events |
| GET | `/thermal-events/{id}` | Get a single thermal event |
| GET | `/thermal-events/{id}/history` | Historical detections for an event |
| GET | `/map/hotspots` | Hotspot data formatted for GIS map |
| GET | `/history/data-quality` | Comprehensive historical data quality report |
| GET | `/history/statistics` | Historical thermal statistics |
| GET | `/history/location/{lat}/{lon}/statistics` | Location-specific historical statistics |
| GET | `/history/location/{lat}/{lon}/baseline` | Location-specific historical baseline |
| POST | `/history/location/{lat}/{lon}/compare` | Compare current observations against baseline |
| GET | `/history/event/{event_id}/profile` | Get computed Thermal DNA profile for an event |
| POST | `/history/event/{event_id}/profile` | Compute and persist Thermal DNA profile for an event |

---

## Current Dataset Status

| Metric | Value |
|--------|-------|
| Total observations | 789 |
| Total thermal events | 618 |
| New observations (this session) | 124 |
| New events (this session) | 110 |
| New orphan events | 0 |
| New observation_count mismatches | 0 |
| New observations with correct FIRMS source | 124/124 (N20) |
| Legacy orphan events (preserved) | 94 |
| Legacy UNKNOWN sources (preserved) | 665 |

---

## Current Dataset Limitations

The current dataset has limited historical depth. Do NOT pretend it is sufficient for a statistically meaningful baseline. If insufficient history exists, the system marks the result as `INSUFFICIENT_HISTORY` and does not fabricate data, Thermal DNA, or baselines.

---

## Explicitly OUT OF SCOPE

- ML training
- Supervised classification
- ML anomaly detection (Isolation Forest, etc.)
- Replacement of the risk engine
- Synthetic labels/data
- Frontend redesign (only integrate historical intelligence into existing UI)
- Geographic search
- PDF reports
- Database rebuild
- Deleting the 94 legacy orphan events
- Rewriting the 665 historical UNKNOWN sources without evidence

---

## License

Developed for SIH 2026. Internal NTRO / academic use.

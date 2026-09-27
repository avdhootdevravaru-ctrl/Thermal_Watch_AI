# ThermalWatch AI

## Current real FIRMS prototype (Windows)

The normal local configuration uses a real NASA FIRMS India capture. A successful
fetch is preserved as raw CSV plus an audit report and cleaned JSONL. The same
validator and spatial/temporal clustering code feeds event formation, Thermal
DNA, operational risk, an unsupervised Isolation Forest prototype and SHA-256
evidence. The dashboard labels captured data **FIRMS SNAPSHOT** because this
machine currently has no running PostgreSQL/PostGIS service. Press **Refresh
FIRMS feed** to make a new NASA request. The map and event pages then use the
newly captured observations. No synthetic observations enter this path.

```powershell
cd C:\Users\tejap\Thermal_Watch_AI\backend
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Set FIRMS_MAP_KEY privately in .env, DEMO_MODE=false,
# FIRMS_SNAPSHOT_PATH=data/firms_latest_raw.csv, FIRMS_AREA=IND.
.\.venv\Scripts\python.exe -m app.ingestion.capture
.\.venv\Scripts\python.exe -m app.ml.train_anomaly
# Set ML_MODEL_PATH=models/firms_anomaly.joblib in .env.
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

In another terminal, run `npm run dev` from `frontend`, then open
<http://localhost:3000>. The capture command requires network access and a
valid NASA FIRMS key. Raw data and the model artifact are ignored by Git.
The model is **unlabelled and unvalidated**: its signed decision score ranks
unusual event patterns in the capture, without fire probabilities, accuracy
claims or causal classification. Risk is a separate explainable priority
heuristic. A short capture cannot establish a historical baseline.
VIIRS high/nominal/low detection confidence remains categorical in the UI;
it is never converted into a made-up percentage.

Evidence is available at `/evidence/{event_id}` and verifiable at
`/evidence/{event_id}/verify`. An analyst may add an optional local receipt with
`POST /evidence/{event_id}/anchor-local`. `/blockchain/status` explicitly reports
`NOT_CONFIGURED`; local receipts are not on-chain transactions.

For a video, show: Refresh FIRMS feed → Analytics validation counts → select a
map marker/priority event → event Thermal DNA and risk factors → Model page
provenance → Evidence ID/hash → anchor locally and verify → database and
blockchain limitations. If network access fails during recording, the saved
real FIRMS capture remains available and is labelled with its capture time.

## Optional synthetic fallback (Windows)

The application can run with an explicit, read-only synthetic dataset when
PostgreSQL/PostGIS is unavailable. The sample never enters the live database
and every demo observation uses `DEMO_SYNTHETIC` provenance. The interface
labels the mode **DEMO DATA**. Seven India scenarios exercise the existing
clustering, persistence, risk, map, event-detail and Thermal DNA code. Their
historical baselines remain `INSUFFICIENT_HISTORY`; these are not NASA FIRMS
detections or validated fire-risk predictions. A reproducible synthetic
weak-label classifier can be loaded for the demo. Its model votes are
uncalibrated and cannot establish fire cause or scientific accuracy.

```powershell
cd C:\Users\tejap\Thermal_Watch_AI\backend
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Set DEMO_MODE=true in backend/.env. To enable the optional demo classifier:
.\.venv\Scripts\python.exe -m app.ml.bootstrap --output models\demo_weak_classifier.joblib
# Set ML_MODEL_PATH=models/demo_weak_classifier.joblib in backend/.env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

In a second terminal:

```powershell
cd C:\Users\tejap\Thermal_Watch_AI\frontend
npm run dev
```

Open <http://localhost:3000>. The Vite `/api` proxy points to port 8000.
The demo dataset is generated in `backend/app/demo.py`; no database write
is needed. The weak-label artifact is excluded from Git and can be regenerated
with the command above. If absent, classification uses the rule fallback.
To use PostgreSQL/PostGIS persistence, set `DEMO_MODE=false`, clear `FIRMS_SNAPSHOT_PATH`,
configure `DATABASE_URL` and `FIRMS_MAP_KEY` in `backend/.env`, start
PostgreSQL with PostGIS, create the `thermalwatch` database and PostGIS
extension, then run `python -m app.db.init_db` from `backend` before starting
the API. The synthetic weak-label model is never used in this mode. Classification
uses an eligible trusted model artifact or the rule fallback.
Operational risk remains rule-based in both modes.
The FIRMS Area API accepts a bounding box or `world` and 1–5 days per
request ([NASA FIRMS Area API](https://firms.modaps.eosdis.nasa.gov/api/area/)).
The client maps legacy `IND` to an India bounding box, then applies the
existing India filter before storage.

### Demonstration flow

1. Open <http://localhost:3000/>. Point out the **DEMO DATA** label, six
   activity KPIs, seven clustered event markers and priority queue.
2. Use **Focus on map** for Event #9001, then click its card to open the
   investigation with model votes, contributing measurements, Thermal
   DNA, unavailable historical baseline and separate operational risk.
3. Open **Events** and filter by risk, status or classification. Event #9005
   shows a lower-priority, shorter-lived scenario.
4. Show <http://127.0.0.1:8000/health/model> and
   <http://127.0.0.1:8000/docs> for model provenance and API contracts.

### Optional supervised classifier

`backend/app/ml/classifier.py` extracts event-level features from actual
FIRMS-compatible fields: brightness, secondary brightness, FRP, scan/track,
day/night, confidence, duration, temporal trend, spatial stability/spread,
recurrence and persistence. Missing
measurements and unavailable historical/facility context remain `null` in
API responses; preprocessing imputes only model inputs.
`backend/app/ml/bootstrap.py` generates deterministic synthetic temporal
patterns in three non-causal classes for the demo artifact. Its 180 weak
labels are not field truth; no accuracy evaluation is claimed.
`backend/app/ml/train.py` accepts independently reviewed event labels in JSONL:

```json
{"label":"industrial_fire","observations":[{"timestamp":"2026-01-01T12:00:00Z","intensity":390,"confidence":90,"latitude":21.1,"longitude":79.0,"metadata":{"frp":20}}]}
```

Accepted labels are the non-`unknown` values of the existing `Classification`
enum in `backend/app/db/models.py`. Supply at least 30 labeled events, with
at least 10 per class, from independent review. Rule-generated or demo labels
must not be used for training. From `backend`, train with:

```powershell
.\.venv\Scripts\python.exe -m app.ml.train --dataset reviewed_events.jsonl --output models\event_classifier.joblib --label-provenance "Independent domain review"
```

Set `ML_MODEL_PATH=models/event_classifier.joblib` in `backend/.env` and
restart the API to use the trained model in **live mode**. Model files must
come from a trusted local source because joblib uses pickle. The GET
`/thermal-events/{id}/classification` endpoint returns the class, raw model
votes or heuristic scores, feature values, model status/version, local feature
sensitivity and global feature importance. GET `/health/model` reports the
model type, version, feature version, training source, calibration, validation,
fallback status and provenance.
The event detail page displays the classification beside the separate
rule-based risk score. Probabilities are uncalibrated prototype outputs;
deploy a supervised model only after independent held-out evaluation. Demo
mode accepts only the synthetic weak-label artifact or the rule fallback.

The read-only `/health/database` endpoint reports whether PostGIS is reachable
in live mode; in demo mode it explicitly reports that no database is used.
`python -m app.db.init_db` enables the PostGIS extension where permitted and
creates the current ORM schema. Existing databases need a separate migration
plan if their tables predate these models. Run backend checks with
`.\.venv\Scripts\python.exe -m pytest -q` and frontend checks with
`npm run build`.

### System flow for the presentation

1. **Input:** NASA FIRMS Area API observations in live mode; explicitly
   synthetic `DEMO_SYNTHETIC` scenarios in demo mode.
2. **Ingestion and cleaning:** `app/ingestion/firms_client.py` fetches the
   configured region and days; `normalizer.py` validates coordinates, time,
   brightness and optional FRP. Duplicate observations are skipped at storage.
3. **Geospatial processing:** `app/processing/clustering.py` groups nearby
   observations into events. `persistence.py` derives active days, detection
   frequency, temporal trend and spatial variance.
4. **Event intelligence:** `app/ml/classifier.py` extracts the same feature
   schema for the demo weak-label model or a reviewed supervised model. Model
   input imputation does not replace missing values in the API. If no eligible
   model is loaded, it uses the existing rule classifier.
5. **Operational priority:** `app/processing/risk.py` scores detection count,
   persistence, duration, trend and thermal intensity independently of class
   votes. The score prioritizes review; it is not a fire probability.
6. **History and display:** Thermal DNA summarizes observed temporal,
   brightness and spatial patterns. Historical baseline comparison remains
   unavailable until sufficient real observations exist. FastAPI serves the
   map, queue, investigation and provenance panels to React.

The current demo has no independently validated labels or accuracy metrics.
Live operation requires PostgreSQL/PostGIS, a FIRMS key and reviewed labels
before a supervised classifier can make operational claims.

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

# IGNIS: real FIRMS intelligence workflow

Run these commands on `tej-dashboard` from PowerShell. The local snapshot path
lets the dashboard work without PostgreSQL. Keep the NASA FIRMS key in
`backend/.env`; never put it in the frontend or commit it.

```powershell
cd C:\Users\tejap\Thermal_Watch_AI\backend
# One-time setup if needed: Copy-Item .env.example .env
# Set DEMO_MODE=false, FIRMS_MAP_KEY=<private key>,
# FIRMS_SNAPSHOT_PATH=data/firms_latest_raw.csv, FIRMS_AREA=IND in .env.
.\.venv\Scripts\python.exe -m app.ingestion.capture
.\.venv\Scripts\python.exe -m app.ml.train_anomaly
.\.venv\Scripts\python.exe -m app.ml.train_weak_firms
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the frontend in a second PowerShell window:

```powershell
cd C:\Users\tejap\Thermal_Watch_AI\frontend
npm install
npm run build
npm run dev
```

Open <http://localhost:3000/> and <http://127.0.0.1:8000/docs>. The capture
command requests real VIIRS detections from NASA FIRMS, validates and cleans
them, and retains the last valid capture on fetch failure. The backend clusters
those detections into events and computes Thermal DNA, an Isolation Forest
anomaly score, a separate weak classifier output, rule-based risk, and evidence.
Use **Refresh FIRMS feed** in the dashboard for a new capture. Retrain the
models after refresh when you want their provenance to match that capture.
The API warns when the classifier artifact was trained on a different capture.

## What the classifier actually predicts

The supervised target is **whether a thermal event cluster is observed again on
a later calendar day within the capture**. Eligible events begin at least two
calendar days before the latest captured observation, allowing one full
following calendar day. `multi_day_recurrence` and `single_day_observed` are
observation-derived weak labels, not reviewed fire or source labels. A missed
satellite detection does not prove heat stopped. The input uses only first-day
measurements; event clustering and the small, single-capture random split still
limit generalization. The model is not suitable for operational fire alerts.

`app.ml.train_weak_firms` fits a median imputer and 200-tree
`RandomForestClassifier` with `min_samples_leaf=2`, balanced subsampling and
seed 42. Its 15 first-day features are observation count, duration, temporal
trend, spatial stability, mean/max brightness, brightness variance, mean/max
FRP, FRP variance, mean secondary brightness, mean scan, mean track, night
fraction and spatial spread. Missing model inputs are imputed; original
missing values remain visible in the API. The classifier is independent of the
existing Isolation Forest and operational risk rules.

The current local capture produced 459 validated detections and 317 clusters.
Of those, 76 events met the follow-up window: 26 later-day and 50 single-day
observed. A stratified seed-42 split trained on 57 events and held out 19.
Measured held-out metrics: accuracy **0.5263**, balanced accuracy **0.4762**,
later-day precision **0.3333**, recall **0.2857**, F1 **0.3077**; macro F1
**0.4738**. Confusion matrix, in class order `[multi_day_recurrence,
single_day_observed]`, is `[[2, 5], [4, 8]]`. Five-fold training-only cross
validation accuracy averaged **0.6652**. These are agreement with weak labels
from the same capture, not accuracy against independent ground truth.

The trusted local model is `backend/models/firms_recurrence.joblib`, with
human-readable `firms_recurrence.metadata.json`. The metadata records feature
schema, capture and dataset hashes, training time, split sizes, metrics, model
version and artifact SHA-256. Inference rejects incompatible artifacts. Never
load a joblib file from an untrusted source. Model class scores are uncalibrated;
`prediction_probability_if_calibrated` is `null`. Per-event explanations show
how replacing one feature with its training median changes the selected class
score. This is local model sensitivity, not a causal explanation.

## API and demo checks

From PowerShell after the API is running:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/ingestion/status
Invoke-RestMethod http://127.0.0.1:8000/firms/status
Invoke-RestMethod http://127.0.0.1:8000/health/model
Invoke-RestMethod http://127.0.0.1:8000/thermal-events
Invoke-RestMethod http://127.0.0.1:8000/map/hotspots
Invoke-RestMethod http://127.0.0.1:8000/thermal-events/59639849
Invoke-RestMethod http://127.0.0.1:8000/thermal-events/59639849/weak-classification
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/classification -ContentType 'application/json' -Body '{"event_id":59639849}'
Invoke-RestMethod http://127.0.0.1:8000/thermal-events/59639849/risk
Invoke-RestMethod http://127.0.0.1:8000/history/statistics
Invoke-RestMethod http://127.0.0.1:8000/evidence/59639849
Invoke-RestMethod http://127.0.0.1:8000/evidence/59639849/verify
Invoke-RestMethod http://127.0.0.1:8000/blockchain/status
```

Event IDs change when a new capture changes clustering. For a demo, choose an
ID returned by `/thermal-events`. The event page links observations, Thermal
DNA, anomaly, the weak classifier, risk and SHA-256 evidence. `GET
/firms/status` reports the source, capture time, latest observation freshness,
validation counts and storage mode. A saved capture is marked `is_live: false`;
freshness describes the age of the observation, not a streaming connection.
If refresh fails, the previous valid CSV remains in use and the dashboard shows
the failure. The Events page filters the complete capture and presents 36
matching events per page.

`POST
/evidence/{id}/anchor-local` adds a **local file hash-chain receipt** for the
current content. Verify it using `/evidence/{id}/verify`; old receipts stay in
the append-only chain when an event or model changes, while the current content
requires a new receipt. The local receipt is **not** a blockchain transaction.
`/blockchain/status` reports on-chain verification unavailable when no provider
is configured. `/health/database` reports PostgreSQL/PostGIS availability;
the snapshot workflow never claims database persistence.

The API's existing `/thermal-events/{id}/classification` remains available as
the anomaly/rule fallback or independently trained supervised path. The new
`/thermal-events/{id}/weak-classification` and `POST /classification` add the
real FIRMS recurrence model without changing that contract. In demo mode, the
real-FIRMS classifier returns HTTP 409; if its artifact is missing or
incompatible, it returns HTTP 503.

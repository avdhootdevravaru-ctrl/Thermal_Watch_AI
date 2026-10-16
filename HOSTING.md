# Thermal Watch.AI hosting

The production Blueprint in `render.yaml` deploys:

- the Vite dashboard as a Render static site;
- the FastAPI API as a Render web service in Singapore;
- PostgreSQL/PostGIS on Render, connected to the backend automatically through
  the Blueprint-managed `DATABASE_URL`.

The checked-in NASA FIRMS CSV is the same public capture used by the verified
local dashboard. The backend start command applies the Alembic schema and
idempotently persists that capture into PostGIS before starting Uvicorn.

## Required secrets

Enter these only in the Render Blueprint form. Never add them to this file or
to Git:

- `FIRMS_MAP_KEY`: the NASA FIRMS MAP_KEY used for fresh ingestion.

On-chain anchoring stays disabled unless a contract and a dedicated testnet
private key are configured directly in Render. Evidence generation,
verification, local anchoring, and blockchain status remain available.

## Public endpoints

- Dashboard: `https://thermal-watch-ai-sih26162.onrender.com`
- API: `https://thermal-watch-ai-sih26162-api.onrender.com`
- Swagger: `https://thermal-watch-ai-sih26162-api.onrender.com/docs`

These URLs become valid only after the Render Blueprint has deployed
successfully. If Render reports a global name collision, use the actual service
hostnames it assigns and update `CORS_ORIGINS` and `VITE_API_BASE_URL` in the
Render dashboard, then redeploy both services.

## Free-tier behavior

The static site is served from Render's CDN. A free Render web service sleeps
after inactivity, so the first API request can take about one minute. Render's
free PostgreSQL database expires after 30 days and has no backups. The free web
service also has an ephemeral filesystem, so local evidence anchor files reset
after a restart; generated evidence packages and verification are deterministic,
and PostGIS data remains stored in PostgreSQL while the database is active.

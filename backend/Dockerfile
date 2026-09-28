FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY models ./models
COPY scripts ./scripts
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["sh", "-c", "python scripts/setup_database.py && if [ ! -s data/firms_latest_raw.csv ]; then python -m app.ingestion.capture; fi && python scripts/ingest_snapshot.py && python -m app.ml.train_anomaly && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

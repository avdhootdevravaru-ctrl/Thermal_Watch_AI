"""Fetch, validate, and preserve a genuine NASA FIRMS CSV for local replay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.ingestion.firms_client import FirmsClient
from app.ingestion.validation import validate_firms_csv


def capture_firms_to_files(*, source: str, area: str, days: int, path: Path):
    if not settings.FIRMS_MAP_KEY or settings.FIRMS_MAP_KEY.startswith("YOUR_"):
        raise ValueError("FIRMS_MAP_KEY is not configured")
    client = FirmsClient(settings.FIRMS_MAP_KEY, satellite=source, area=area, days=days)
    raw_csv = client.fetch_csv()
    accepted, report = validate_firms_csv(raw_csv, source=source)
    if not accepted:
        raise ValueError("FIRMS returned no valid observations; prior capture retained")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(raw_csv, encoding="utf-8")
    temporary.replace(path)
    captured = datetime.now(timezone.utc)
    path.with_suffix(".json").write_text(json.dumps({
        "captured_at": captured.isoformat(), "source": source,
        "area": client.area, "days": days, "provider": "NASA FIRMS Area API",
        "database_persisted": False, "validation": report.as_dict(),
    }), encoding="utf-8")
    path.with_name("firms_latest_clean.jsonl").write_text(
        "".join(json.dumps(row, default=str) + "\n" for row in accepted), encoding="utf-8")
    return report, captured


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=settings.FIRMS_SATELLITE)
    parser.add_argument("--area", default=settings.FIRMS_AREA)
    parser.add_argument("--days", type=int, default=settings.FIRMS_DAYS)
    parser.add_argument("--output", type=Path, default=Path(settings.FIRMS_SNAPSHOT_PATH or "data/firms_latest_raw.csv"))
    args = parser.parse_args()
    try:
        report, captured = capture_firms_to_files(source=args.source, area=args.area, days=args.days, path=args.output)
    except Exception as exc:
        # Provider exceptions can contain a URL with the map key in its path.
        print(f"NASA FIRMS capture failed ({type(exc).__name__}); existing capture retained.")
        raise SystemExit(1)
    print(f"NASA FIRMS capture at {captured.isoformat()}: {report.records_received} received, "
          f"{report.records_accepted} accepted, {report.records_rejected} rejected; saved {args.output}")

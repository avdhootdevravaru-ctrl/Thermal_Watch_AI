"""FIRMS observation normalizer.

Maps FIRMS CSV fields into the internal ThermalObservation schema.
Used by the ingestion pipeline before rows are upserted to PostgreSQL.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# FIRMS → internal schema column mapping
# The FIRMS CSV header has many columns; we only keep the ones we need.
COLUMN_MAP: Dict[str, str] = {
    # date + time → timestamp
    "date": "timestamp",
    "time": "timestamp",

    # Position
    "latitude": "latitude",
    "longitude": "longitude",

    # Thermal
    "brightness_temperature": "intensity",
    "bright_t31": "intensity",
    "bright_ti4": "intensity",

    # Confidence (varies by sensor)
    "confidence": "confidence",

    # Source / provenance — note: the `satellite` column in FIRMS CSVs contains short
# identifiers (e.g. "N20") rather than product names. The `source` field set by
# firms_client._parse_csv (the configured product, e.g. "VIIRS_NOAA20_NRT") is
# the authoritative provenance indicator. We keep `satellite` in the map so
# legacy rows that only have a `satellite` key still get a source, but the
# normalizer prefers the explicit `source` key when present.
    "satellite": "source",
}


def normalize_observation(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Take a raw FIRMS observation dict and normalise it for the DB schema.

    Returns a dict with keys: timestamp, latitude, longitude, intensity, confidence, source, sensor, metadata,
    and _invalid_coordinates (bool flag indicating if coordinates were out of valid range).
    Missing values become None; types are coerced; dates are parsed to datetime.
    """
    obs: Dict[str, Any] = {}
    invalid_coordinates = False

    # Timestamp: combine date+time if possible. Missing or unparsable timestamps
    # stay None so the ingestion pipeline can reject them as invalid data.
    # Supports both legacy (date + time) and modern (acq_date + acq_time) FIRMS formats.
    raw_ts = raw.get("date") or raw.get("timestamp") or raw.get("acq_date")
    raw_time = raw.get("time") or raw.get("acq_time")
    if raw_ts:
        # FIRMS date YYYYMMDD + time HHMMSS → datetime
        try:
            dt = _parse_firm_ts(raw_ts, raw_time or "")
            obs["timestamp"] = dt.replace(tzinfo=timezone.utc) if hasattr(dt, "tzinfo") and dt.tzinfo is None else dt
        except Exception as e:
            logger.warning("Failed to parse FIRMS timestamp %s: %s", raw_ts, e)
            obs["timestamp"] = None
    else:
        obs["timestamp"] = None

    # Latitude
    lat = raw.get("latitude")
    try:
        obs["latitude"] = float(lat) if lat is not None and str(lat).strip() != "" else None
    except (ValueError, TypeError):
        obs["latitude"] = None
        invalid_coordinates = True

    # Longitude
    lon = raw.get("longitude")
    try:
        obs["longitude"] = float(lon) if lon is not None and str(lon).strip() != "" else None
    except (ValueError, TypeError):
        obs["longitude"] = None
        invalid_coordinates = True

    # Coordinate range validation — track if raw values were provided but out of range
    if obs["latitude"] is not None and (not math.isfinite(obs["latitude"]) or not (-90.0 <= obs["latitude"] <= 90.0)):
        logger.warning("Invalid latitude %s outside [-90, 90]", obs["latitude"])
        invalid_coordinates = True
        obs["latitude"] = None
    if obs["longitude"] is not None and (not math.isfinite(obs["longitude"]) or not (-180.0 <= obs["longitude"] <= 180.0)):
        logger.warning("Invalid longitude %s outside [-180, 180]", obs["longitude"])
        invalid_coordinates = True
        obs["longitude"] = None

    obs["_invalid_coordinates"] = invalid_coordinates

    # Brightness temperature is measured in K; FRP is a distinct MW measure.
    raw_int = next((raw[key] for key in ("intensity", "bright_ti4", "brightness_temperature", "brightness", "bright_t31")
                    if raw.get(key) is not None and str(raw[key]).strip() != ""), None)
    if raw_int is not None and str(raw_int).strip() != "":
        try:
            value = float(raw_int)
            obs["intensity"] = value if math.isfinite(value) else None
        except (ValueError, TypeError):
            obs["intensity"] = None
    else:
        obs["intensity"] = None

    # Confidence — VIIRS NRT uses 'h'/'l'/'n'; MODIS uses numeric values
    raw_conf = raw.get("confidence")
    obs["confidence"] = _parse_confidence(raw_conf)

    # Source / sensor
    obs["source"] = raw.get("source") or raw.get("satellite") or "UNKNOWN"
    obs["sensor"] = raw.get("sensor") or raw.get("satellite")

    # Keep FIRMS optional measurements at the top metadata level. The HTTP
    # parser already supplies a nested metadata dict; flatten that first.
    nested_metadata = raw.get("metadata")
    obs["metadata"] = dict(nested_metadata) if isinstance(nested_metadata, dict) else {}
    obs["metadata"].update({
        k: v for k, v in raw.items()
        if k not in (
            "date", "time", "acq_date", "acq_time", "timestamp",
            "latitude", "longitude", "intensity", "confidence",
            "source", "satellite", "sensor", "metadata",
        )
    })
    if str(raw_conf).strip().lower() in {"h", "n", "l"}:
        obs["metadata"]["confidence_category"] = {"h": "high", "n": "nominal", "l": "low"}[str(raw_conf).strip().lower()]

    return obs


def _parse_confidence(raw: Any) -> Optional[float]:
    """Return only genuine numeric FIRMS confidence percentages.

    VIIRS NRT uses categorical labels: 'h' (high), 'l' (low), 'n' (nominal).
    MODIS NRT uses numeric values (0–100).

    VIIRS categories are not percentages, so they remain null here and are
    retained separately in metadata as confidence_category.
    """
    if raw is None:
        return None
    val = str(raw).strip().lower()
    if not val:
        return None
    if val in {"h", "n", "l"}:
        return None
    # Numeric (MODIS): try direct float conversion
    try:
        value = float(raw)
        return value if math.isfinite(value) and 0 <= value <= 100 else None
    except (ValueError, TypeError):
        return None


def _parse_firm_ts(date_str: str, time_str: str) -> datetime:
    """Parse FIRMS date+time → timezone-aware datetime.

    Modern FIRMS API (/api/area/csv) formats:
        date_str: YYYY-MM-DD (e.g. 2026-09-04) or full ISO "YYYY-MM-DD HH:MM:SS"
        time_str: HHMM (e.g. 39, 1430)

    Legacy MODIS formats also accepted:
        date_str: YYYYMMDD  (e.g. 20260815)
        time_str: HHMMSS    (e.g. 143000)
    """
    if not date_str and not time_str:
        raise ValueError("Empty date and time strings")

    date_str = str(date_str).strip()
    time_str = str(time_str).strip()

    # Fast path: full ISO datetime (e.g. "2026-09-04T10:20:00+00:00" or "2026-09-04 10:20:00")
    if " " in date_str or "T" in date_str:
        iso = date_str.replace(" ", "T")
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass

    # Fast path: date contains a time portion (e.g. "2026-09-04 10:20:00")
    if " " in date_str:
        return datetime.fromisoformat(date_str.replace(" ", "T")).replace(tzinfo=timezone.utc)

    if not date_str:
        raise ValueError("Empty date string")

    # Parse date
    if "-" in date_str and len(date_str) == 10:
        year, month, day = date_str.split("-")
        year, month, day = int(year), int(month), int(day)
    elif len(date_str) == 8 and date_str.isdigit():
        year, month, day = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
    else:
        raise ValueError(f"Unrecognised FIRMS date format: {date_str!r}")

    # FIRMS uses HHMM; CSV readers may strip leading zeroes.
    if not time_str or time_str == "0":
        hour, minute, second = 0, 0, 0
    elif time_str.isdigit():
        if len(time_str) <= 4:
            padded = time_str.zfill(4)
            hour, minute, second = int(padded[:2]), int(padded[2:]), 0
        elif len(time_str) == 6:
            # HHMMSS (legacy MODIS)
            hour, minute, second = int(time_str[:2]), int(time_str[2:4]), int(time_str[4:6])
        else:
            raise ValueError(f"Unrecognised FIRMS time format: {time_str!r}")
    else:
        raise ValueError(f"Unrecognised FIRMS time format: {time_str!r}")

    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize an entire pandas DataFrame of FIRMS observations.

    Useful when ingesting the full CSV as a DataFrame rather than row-by-row.
    Returns a new DataFrame with normalized column names and types.
    """
    df = df.copy()

    # Rename known columns. Both modern (acq_date / acq_time / bright_ti4) and
    # legacy (date / time / brightness_temperature / bright_t31) FIRMS formats supported.
    rename_map = {
        "acq_date": "timestamp",      # modern FIRMS /api/area/csv
        "date": "timestamp",          # legacy MODIS
        "latitude": "latitude",
        "longitude": "longitude",
        "bright_ti4": "intensity",    # VIIRS brightness temp
        "brightness_temperature": "intensity",  # MODIS
        "brightness": "intensity",              # FIRMS MODIS Area API
        "bright_t31": "intensity",    # MODIS legacy
        "confidence": "confidence",
        "satellite": "source",
    }
    existing_map = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=existing_map)

    # Combine date+time into a single timestamp column
    if "timestamp" in df.columns and "acq_time" in df.columns:
        # Modern FIRMS: timestamp is YYYY-MM-DD; combine with HHMM time
        df["timestamp"] = pd.to_datetime(
            df["timestamp"].astype(str) + " " + df["acq_time"].astype(str).str.zfill(4),
            format="%Y-%m-%d %H%M",
            errors="coerce",
        )
        df = df.drop(columns=["acq_time"])
    elif "timestamp" in df.columns and "time" in df.columns:
        # Legacy MODIS: both YYYYMMDD and HHMMSS
        df["timestamp"] = pd.to_datetime(
            df["timestamp"].astype(str) + df["time"].astype(str),
            format="%Y%m%d%H%M%S",
            errors="coerce",
        )
        df = df.drop(columns=["time"])
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Confidence: VIIRS uses 'h'/'l'/'n'; MODIS uses numeric. Map to 0–100 scale.
    if "confidence" in df.columns:
        df["confidence"] = df["confidence"].map(_parse_confidence)

    # Coerce numeric types
    for col in ["latitude", "longitude", "intensity"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Ensure source is filled
    if "source" in df.columns:
        df["source"] = df["source"].fillna("UNKNOWN")

    # Coordinate range validation
    if "latitude" in df.columns:
        invalid_lat = (df["latitude"] < -90.0) | (df["latitude"] > 90.0)
        if invalid_lat.any():
            logger.warning("Invalid latitudes outside [-90, 90]: %d rows", invalid_lat.sum())
            df.loc[invalid_lat, "latitude"] = np.nan
    if "longitude" in df.columns:
        invalid_lon = (df["longitude"] < -180.0) | (df["longitude"] > 180.0)
        if invalid_lon.any():
            logger.warning("Invalid longitudes outside [-180, 180]: %d rows", invalid_lon.sum())
            df.loc[invalid_lon, "longitude"] = np.nan

    # Drop rows where we can't even locate the observation
    df = df.dropna(subset=["latitude", "longitude", "timestamp"])

    return df


if __name__ == "__main__":
    # Quick sanity-check when run standalone
    import json
    sample = {
        "date": "20260815",
        "time": "143000",
        "latitude": "-15.3",
        "longitude": "145.7",
        "confidence": "high",
        "brightness_temperature": "320.5",
        "frp": "12.5",
        "satellite": "VIIRS_NOAA20_NRT",
    }
    normalized = normalize_observation(sample)
    print("Normalized observation:")
    print(json.dumps(normalized, default=str, indent=2))

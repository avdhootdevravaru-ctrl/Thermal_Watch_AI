"""Validate and deduplicate raw NASA FIRMS CSV rows before event formation.

Adapted from the Ignis team's row-level validation ideas.  This module keeps
missing optional measurements as null and reports every rejected row by reason.
It is shared by the PostGIS ingestion path and the local FIRMS snapshot path.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from app.ingestion.firms_client import FirmsClient
from app.ingestion.normalizer import normalize_observation


@dataclass
class ValidationReport:
    records_received: int = 0
    records_accepted: int = 0
    records_rejected: int = 0
    duplicates_removed: int = 0
    invalid_coordinates: int = 0
    invalid_timestamps: int = 0
    invalid_brightness: int = 0
    invalid_frp: int = 0
    invalid_scan: int = 0
    invalid_track: int = 0
    invalid_confidence: int = 0
    missing_values: dict[str, int] = field(default_factory=dict)
    rejection_reasons: dict[str, int] = field(default_factory=dict)
    earliest_observation: str | None = None
    latest_observation: str | None = None

    def as_dict(self) -> dict:
        return vars(self).copy()


def _measurement(raw: dict, keys: tuple[str, ...], low: float, high: float) -> tuple[float | None, str | None]:
    value = next((raw[key] for key in keys if raw.get(key) is not None
                  and str(raw[key]).strip().lower() not in {"", "-", "na", "n/a", "null"}), None)
    if value is None:
        return None, None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "MALFORMED"
    if not math.isfinite(number) or not low <= number <= high:
        return None, "OUT_OF_RANGE"
    return number, None


def validate_firms_csv(csv_text: str, *, source: str) -> tuple[list[dict], ValidationReport]:
    """Return normalized observations and a reproducible row-level audit."""
    source = source.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_]{1,50}", source):
        raise ValueError("Invalid FIRMS product source")
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    required_headers = {"latitude", "longitude", "acq_date", "acq_time"}
    if not reader.fieldnames or not required_headers.issubset(reader.fieldnames):
        raise ValueError("FIRMS CSV lacks required coordinate or acquisition columns")

    report = ValidationReport()
    reasons: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    seen: set[tuple[float, float, datetime, str]] = set()
    accepted: list[dict] = []
    for raw in reader:
        report.records_received += 1
        reason = "MALFORMED_RECORD" if None in raw else None
        lat, lat_error = _measurement(raw, ("latitude",), -90, 90)
        lon, lon_error = _measurement(raw, ("longitude",), -180, 180)
        if lat_error or lon_error or (lat == 0 and lon == 0):
            reason = "INVALID_COORDINATES"
            report.invalid_coordinates += 1
        elif lat is None or lon is None:
            reason = "MISSING_COORDINATES"
            missing["coordinates"] += 1

        timestamp = FirmsClient._firm_date_time(raw.get("acq_date", ""), raw.get("acq_time", ""))
        if timestamp is None:
            reason = reason or "INVALID_TIMESTAMP"
            report.invalid_timestamps += 1

        brightness, brightness_error = _measurement(
            raw, ("bright_ti4", "brightness", "brightness_temperature", "bright_t31"), 200, 500,
        )
        if brightness_error:
            reason = reason or "INVALID_BRIGHTNESS"
            report.invalid_brightness += 1
        elif brightness is None:
            missing["brightness"] += 1

        frp, frp_error = _measurement(raw, ("frp", "FRP"), 0, 15000)
        if frp_error:
            reason = reason or "INVALID_FRP"
            report.invalid_frp += 1
        elif frp is None:
            missing["frp"] += 1

        for field_name in ("scan", "track"):
            measurement, measurement_error = _measurement(raw, (field_name,), 0, 20)
            if measurement is not None and measurement <= 0:
                measurement_error = "OUT_OF_RANGE"
            if measurement_error:
                reason = reason or f"INVALID_{field_name.upper()}"
                setattr(report, f"invalid_{field_name}", getattr(report, f"invalid_{field_name}") + 1)
            elif measurement is None:
                missing[field_name] += 1

        confidence = str(raw.get("confidence") or "").strip().lower()
        if confidence in {"", "-", "unknown", "na", "n/a", "null"}:
            missing["confidence"] += 1
        elif confidence not in {"h", "n", "l"}:
            _, confidence_error = _measurement(raw, ("confidence",), 0, 100)
            if confidence_error:
                reason = reason or "INVALID_CONFIDENCE"
                report.invalid_confidence += 1

        if reason is None:
            fingerprint = (round(lat, 4), round(lon, 4), timestamp, source)
            if fingerprint in seen:
                reason = "DUPLICATE_OBSERVATION"
                report.duplicates_removed += 1
            else:
                seen.add(fingerprint)

        if reason:
            report.records_rejected += 1
            reasons[reason] += 1
            continue

        normalized = normalize_observation({**raw, "source": source, "timestamp": timestamp})
        normalized["intensity"] = brightness
        normalized["metadata"]["frp"] = frp
        normalized["metadata"]["raw_satellite"] = raw.get("satellite")
        accepted.append(normalized)

    report.records_accepted = len(accepted)
    report.missing_values = dict(missing)
    report.rejection_reasons = dict(reasons)
    if accepted:
        report.earliest_observation = min(o["timestamp"] for o in accepted).isoformat()
        report.latest_observation = max(o["timestamp"] for o in accepted).isoformat()
    return accepted, report

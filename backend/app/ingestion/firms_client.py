"""NASA FIRMS HTTP client.

Provides a simple, retry-enabled interface to fetch FIRMS thermal detection data.
Currently supports the MODIS/VIIRS CSV endpoints via `requests` / `httpx`.

NASA FIRMS docs:
  https://earthdata.nasa.gov/earth-observation/data/near-real-time/modis-and-virrs-fire-data
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class FirmsClient:
    """Client for the NASA FIRMS API.

    The FIRMS API serves the MODIS/VIIRS thermal anomaly data as CSV files.
    Docs: https://earthdata.nasa.gov/earth-observation/data/near-real-time/modis-and-virrs-fire-data
    """

    # Base URLs for the different FIRMS APIs
    BASE_URL_MODIS = "https://modis-fir.nascom.nasa.gov"
    BASE_URL_MODERN = "https://firms.modaps.eosdis.nasa.gov"

    def __init__(
        self,
        map_key: str,
        satellite: str = "VIIRS_NOAA20_NRT",
        area: str = "world",
        days: int = 1,
        timeout: int = 60,
    ):
        self.map_key = map_key
        self.satellite = satellite
        self.area = area
        self.days = days
        self.timeout = timeout
        self.base_url = f"{self.BASE_URL_MODERN}/api/area"

    @retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=30),
    )
    def fetch_csv(self) -> str:
        """Fetch the FIRMS CSV data with automatic retries.

        Returns the raw CSV text.
        Raises httpx.HTTPStatusError on persistent failure.
        """
        # NASA FIRMS Area API uses path-style URLs, not query strings.
        # Format: /api/area/csv/{MAP_KEY}/{SOURCE}/{AREA_COORDINATES}/{DAY_RANGE}
        # where AREA_COORDINATES is "world" or a bounding box "west,south,east,north".
        url = (
            f"{self.base_url}/csv/"
            f"{self.map_key}/"
            f"{self.satellite}/"
            f"{self.area}/"
            f"{self.days}"
        )

        logger.info("Fetching FIRMS data: satellite=%s area=%s days=%d", self.satellite, self.area, self.days)

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
            return resp.text

    def fetch_observations(self) -> List[Dict[str, Any]]:
        """Parse FIRMS CSV into a list of observation dicts.

        Returns a list of dicts with keys matching the FIRMS CSV columns,
        normalised to snake_case for downstream use.
        """
        raw_csv = self.fetch_csv()
        observations = self._parse_csv(raw_csv, satellite=self.satellite)
        logger.info("Parsed %d FIRMS observations", len(observations))
        return observations

    def _parse_csv(self, csv_text: str, satellite: str = "UNKNOWN") -> List[Dict[str, Any]]:
        """Parse the raw FIRMS CSV into normalized observation dicts.

        NASA FIRMS VIIRS NRT columns (as returned by /api/area/csv):
            latitude, longitude, bright_ti4, scan, track, acq_date, acq_time,
            satellite, instrument, confidence, version, bright_ti5, frp, daynight

        NASA FIRMS MODIS columns:
            latitude, longitude, brightness_temperature, scan, track, acq_date,
            acq_time, satellite, instrument, confidence, version, bright_t31, frp, daynight

        Both formats share: latitude, longitude, acq_date, acq_time, satellite,
        instrument, confidence (categorical 'h'/'l'/'n' in NRT, numeric in MODIS),
        version, frp, daynight, scan, track.

        Intensity (brightness temperature) differs: 'bright_ti4' (VIIRS) vs
        'brightness_temperature' (MODIS). Both may be present; we pick the first
        available value.

        The ``satellite`` parameter is the FIRMS product source (e.g.
        ``VIIRS_NOAA20_NRT``) which is used for the ``source`` field. This ensures
        provenance is correctly attributed from the configured product, not the
        row-level ``satellite`` CSV column (which contains short identifiers like
        ``N20`` and is unreliable for source tracking).
        """
        reader = csv.DictReader(io.StringIO(csv_text))
        rows: List[Dict[str, Any]] = []

        for row in reader:
            # Timestamp: acq_date (YYYY-MM-DD or sometimes YYYY-MM-DD HH:MM:SS) + acq_time (HHMM)
            # Some NASA rows bundle the date+time in acq_date with empty acq_time.
            date_str = (row.get("acq_date") or row.get("date") or "").strip()
            time_str = (row.get("acq_time") or row.get("time") or "").strip()
            if " " in date_str and not time_str:
                # "2026-09-04 10:20:00" — split into date+time
                date_part, time_part = date_str.split(" ", 1)
                date_str = date_part
                time_str = time_part.replace(":", "").lstrip("0") or "0"

            # Intensity: bright_ti4 (VIIRS) → brightness_temperature (MODIS) → bright_t31 (MODIS legacy)
            raw_int = (
                row.get("bright_ti4")
                or row.get("brightness_temperature")
                or row.get("bright_t31")
            )

            obs = {
                "timestamp": FirmsClient._firm_date_time(date_str, time_str),
                "latitude": float(row["latitude"]) if row.get("latitude") else None,
                "longitude": float(row["longitude"]) if row.get("longitude") else None,
                "intensity": float(raw_int) if raw_int else None,
                "confidence": FirmsClient._parse_confidence(row.get("confidence", "")),
                "source": satellite.upper(),
                "sensor": row.get("instrument") or row.get("satellite"),
                "metadata": {
                    "frp": row.get("frp"),
                    "version": row.get("version"),
                    "daynight": row.get("daynight"),
                    "scan": row.get("scan"),
                    "track": row.get("track"),
                    "instrument": row.get("instrument"),
                    "bright_ti4": row.get("bright_ti4"),
                    "bright_ti5": row.get("bright_ti5"),
                    "bright_t31": row.get("bright_t31"),
                    "brightness_temperature": row.get("brightness_temperature"),
                },
            }
            rows.append(obs)

        return rows

    @staticmethod
    def _parse_confidence(raw: str) -> Optional[float]:
        """Parse FIRMS confidence value to a numeric score.

        VIIRS NRT uses categorical labels: 'h' (high), 'l' (low), 'n' (nominal).
        MODIS NRT uses numeric values (0–100).

        We normalise to 0–100: h=100, n=50, l=0.
        Unknown / empty values return None.
        """
        if not raw:
            return None
        raw = str(raw).strip().lower()
        if raw == "h":
            return 100.0
        if raw == "n":
            return 50.0
        if raw == "l":
            return 0.0
        # Numeric (MODIS): attempt direct float conversion
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _firm_date_time(date_str: str, time_str: str) -> datetime:
        """Combine FIRMS date/time strings into a timezone-aware datetime.

        Modern FIRMS API (/api/area/csv) formats:
            date_str: YYYY-MM-DD (e.g. 2026-09-04) or full ISO "YYYY-MM-DD HH:MM:SS"
            time_str: HHMM (e.g. 39 for 00:39, or 1430 for 14:30)

        Legacy MODIS formats also accepted:
            date_str: YYYYMMDD
            time_str: HHMMSS
        """
        try:
            ds = (date_str or "").strip()
            ts = (time_str or "").strip()

            # Fast path: if ds contains a space, it's a full ISO datetime string
            # e.g. "2026-09-04 10:20:00" — parse directly
            if " " in ds:
                return datetime.fromisoformat(ds.replace(" ", "T")).replace(tzinfo=timezone.utc)

            # Parse date — modern format YYYY-MM-DD
            if "-" in ds and len(ds) == 10:
                year, month, day = ds.split("-")
                year, month, day = int(year), int(month), int(day)
            elif len(ds) == 8 and ds.isdigit():
                year, month, day = int(ds[:4]), int(ds[4:6]), int(ds[6:8])
            else:
                raise ValueError(f"Unrecognised FIRMS date format: {ds!r}")

            # Parse time — real FIRMS /api/area/csv uses HHMM in 24-hour clock
            # (e.g. "1430" = 14:30, "1452" = 14:52). But the API also returns
            # 2-digit values that are "minutes since midnight UTC" (e.g. "39" = 00:39,
            # "56" = 00:56). Legacy MODIS used HHMMSS.
            #
            # Heuristic: 4 digits → HHMM; 2-3 digits → minutes-since-midnight; 6 → HHMMSS.
            if ts.isdigit():
                if len(ts) == 4:
                    # HHMM (e.g. "1430" = 14:30, "1452" = 14:52, "0001" = 00:01)
                    hour, minute, second = int(ts[:2]), int(ts[2:4]), 0
                elif len(ts) in (2, 3):
                    # 2-3 digit "minutes since midnight" (e.g. "39" = 00:39, "145" = 02:25)
                    n = int(ts)
                    if 0 <= n < 1440:
                        hour, minute, second = n // 60, n % 60, 0
                    else:
                        raise ValueError(f"Unrecognised FIRMS time format: {ts!r}")
                elif len(ts) == 6:
                    # HHMMSS (legacy MODIS)
                    hour, minute, second = int(ts[:2]), int(ts[2:4]), int(ts[4:6])
                else:
                    raise ValueError(f"Unrecognised FIRMS time format: {ts!r}")
            elif len(ts) == 0 or ts == "0":
                hour, minute, second = 0, 0, 0
            else:
                raise ValueError(f"Unrecognised FIRMS time format: {ts!r}")

            return datetime(year, month, day, hour, minute, second)
        except (ValueError, TypeError) as e:
            logger.warning("Could not parse FIRMS date/time %s %s: %s", date_str, time_str, e)
            return datetime.now()
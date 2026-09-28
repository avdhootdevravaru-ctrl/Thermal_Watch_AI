"""India point containment backed by the bundled Natural Earth boundary.

The project requests a rectangular FIRMS area for efficient downloads, then
applies this polygon at validation time before clustering, ML, risk, or API
responses. ``covers`` retains points exactly on the boundary.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely.geometry import Point, shape
from shapely.prepared import prep
from sqlalchemy import func


BOUNDARY_PATH = Path(__file__).resolve().parents[1] / "data" / "ne_10m_admin_0_india.geojson"
INDIA_BOUNDARY_SOURCE = (
    "Natural Earth 1:10m Admin 0 Countries, India point of view, public domain"
)


@lru_cache(maxsize=1)
def _geometry() -> Any:
    data = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))
    features = data.get("features", [])
    if len(features) != 1:
        raise RuntimeError("Bundled India boundary must contain exactly one feature")
    geometry = shape(features[0]["geometry"])
    if geometry.is_empty or not geometry.is_valid:
        raise RuntimeError("Bundled India boundary geometry is invalid")
    return geometry


@lru_cache(maxsize=1)
def _prepared_geometry() -> Any:
    return prep(_geometry())


def is_in_india(latitude: float, longitude: float) -> bool:
    """Return whether a WGS84 point falls in or on India's boundary."""
    try:
        point = Point(float(longitude), float(latitude))
    except (TypeError, ValueError):
        return False
    return bool(_prepared_geometry().covers(point))


@lru_cache(maxsize=1)
def _geometry_json() -> str:
    data = json.loads(BOUNDARY_PATH.read_text(encoding="utf-8"))
    return json.dumps(data["features"][0]["geometry"], separators=(",", ":"))


def india_sql_contains(latitude_column: Any, longitude_column: Any) -> Any:
    """Return a PostGIS expression matching centroids inside India."""
    boundary = func.ST_SetSRID(func.ST_GeomFromGeoJSON(_geometry_json()), 4326)
    point = func.ST_SetSRID(func.ST_MakePoint(longitude_column, latitude_column), 4326)
    return func.ST_Covers(boundary, point)

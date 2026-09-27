"""Database schema initialization.

Run this once to create all tables via SQLAlchemy:
    python -m app.db.init_db

The tables use PostGIS geometry columns. The extension must be enabled
before table creation; failure is reported rather than hidden.
"""

from __future__ import annotations

import logging
import sys
from sqlalchemy import text

from app.config import settings
from app.db.base import Base, engine
from app.db import models  # noqa: F401 — imports register models with Base

logger = logging.getLogger(__name__)


def init_schema() -> None:
    """Create all tables defined on the Base class."""
    logger.info("Connecting to database: %s", settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else "[local]")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            Base.metadata.create_all(bind=connection)
        logger.info("Schema created successfully. Tables: %s", list(Base.metadata.tables.keys()))
    except Exception as e:
        logger.error("Failed to create schema: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_schema()

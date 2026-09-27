"""Database connection setup.

Uses SQLAlchemy 2.0 with async-compatible session.
PostGIS geometry columns are exposed through GeoAlchemy2.

The engine and sessionmaker are lazily initialized to allow testing without
requiring a live PostgreSQL connection at import time.
"""

from __future__ import annotations

import os
import threading
from typing import Optional, TYPE_CHECKING

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Lazy initialization: don't create engine at module load time
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None
_lock = threading.RLock()  # RLock (reentrant) — _get_session_factory calls _get_engine while holding the lock


def _get_engine() -> Engine:
    """Lazily create and return the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                # Import here so tests that don't need DB don't pay the import cost
                from app.config import settings
                _engine = create_engine(
                    settings.DATABASE_URL,
                    pool_pre_ping=True,
                    connect_args={"connect_timeout": 3} if settings.DATABASE_URL.startswith("postgresql") else {},
                    echo=False,
                )
    return _engine


def _get_session_factory() -> sessionmaker:
    """Lazily create and return the sessionmaker."""
    global _session_factory
    if _session_factory is None:
        with _lock:
            if _session_factory is None:
                _session_factory = sessionmaker(
                    bind=_get_engine(),
                    autoflush=False,
                    autocommit=False,
                    class_=Session,
                )
    return _session_factory


# Expose a property-based interface so existing code still works
@property
def engine() -> Engine:
    return _get_engine()


# Provide module-level engine/session that delegate lazily
class _LazyEngine:
    """Lazy proxy for the SQLAlchemy engine."""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def __repr__(self):
        return f"<LazyEngine(url=...)>"

    def dispose(self):
        global _engine
        with _lock:
            if _engine is not None:
                _engine.dispose()
                _engine = None


class _LazySessionFactory:
    """Lazy proxy for the sessionmaker."""

    def __call__(self):
        return _get_session_factory()()

    def __getattr__(self, name):
        return getattr(_get_session_factory(), name)


# These replace the module-level globals
engine = _LazyEngine()  # type: ignore
SessionLocal = _LazySessionFactory()  # type: ignore


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def get_db() -> Session:
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

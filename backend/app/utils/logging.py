"""Logging configuration for ThermalWatch AI.

Uses loguru for structured, colored console output and optional file rotation.
"""

from __future__ import annotations

import sys
import re

from loguru import logger

from app.config import settings


def redact_secrets(message: str) -> str:
    """FIRMS places the MAP_KEY in a URL path, including httpx access logs."""
    message = re.sub(r"(/api/area/csv/)[^/\s?]+", r"\1[REDACTED]", message)
    if settings.FIRMS_MAP_KEY:
        message = message.replace(settings.FIRMS_MAP_KEY, "[REDACTED]")
    return message


def setup_logging() -> None:
    """Configure loguru with console and optional file handlers."""
    # Remove default handler
    logger.remove()

    # Console handler with colors
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # Optional file handler (only in production / when configured)
    if settings.APP_ENV == "production":
        logger.add(
            "logs/thermalwatch.log",
            level="INFO",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                "{name}:{function}:{line} | {message}"
            ),
        )

    # Intercept standard logging to loguru
    import logging
    logging.basicConfig(handlers=[], level=0)

    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Get corresponding Loguru level if it exists
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller from where originated the logged message
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            # Exception tracebacks may contain request URLs, so log the safe
            # message only. Never allow a path-style FIRMS key into console or
            # rotating production files.
            logger.opt(depth=depth).log(level, redact_secrets(record.getMessage()))

    logging.basicConfig(handlers=[InterceptHandler()], level=0)

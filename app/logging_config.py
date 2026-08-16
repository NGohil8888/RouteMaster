"""Structured logging configuration for the gateway."""

import logging
import sys
from typing import Any, Dict


class StructuredLogFormatter(logging.Formatter):
    """Custom formatter that produces structured log output."""

    def format(self, record: logging.LogRecord) -> str:
        level = record.levelname
        name = record.name
        message = record.getMessage()
        return f"[{level}] {name}: {message}"


def setup_logging(log_level: str = "INFO") -> None:
    """Configure application logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StructuredLogFormatter())
    root_logger.addHandler(console_handler)

    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
"""Structured logging configuration with secret redaction."""

import logging
import re
import sys
from typing import Any

# Patterns to redact from logs
_REDACT_PATTERNS = [
    re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[a-zA-Z0-9_\-]+", re.IGNORECASE),
    re.compile(r"(Authorization['\"]?\s*[:=]\s*['\"]?\s*Bearer\s+)[a-zA-Z0-9_\-]+", re.IGNORECASE),
]


class RedactingFilter(logging.Filter):
    """Filter that redacts sensitive tokens from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in _REDACT_PATTERNS:
                record.msg = pattern.sub(r"\g<1>***REDACTED***", record.msg)
        if record.args:
            args = tuple(self._redact_arg(a) for a in record.args)
            record.args = args
        return True

    @staticmethod
    def _redact_arg(arg: Any) -> Any:
        if isinstance(arg, str):
            for pattern in _REDACT_PATTERNS:
                arg = pattern.sub(r"\g<1>***REDACTED***", arg)
        return arg


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structured logging with redaction."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root.handlers = [handler]

    # Reduce noise from external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
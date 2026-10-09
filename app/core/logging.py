"""Structured JSON logging configuration and context management."""

from __future__ import annotations

import contextvars
import datetime
import json
import logging
import re
import sys
import traceback
from typing import Any, Dict, Optional

from app.core.config import settings

# Context variable for holding the current request ID across async calls
request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)

# Regex to sanitize credentials from URLs (e.g. redis://:pass@host or postgres://user:pass@host)
CREDENTIALS_REGEX = re.compile(r"://([^:]*):([^@]+)@")


def sanitize_sensitive_data(text: str) -> str:
    """Mask credentials and sensitive strings from logs."""
    if not text:
        return text
    # Mask URL passwords: redis://:secret@host -> redis://:***@host
    sanitized = CREDENTIALS_REGEX.sub(r"://\1:***@", text)
    # Mask API key query parameters or headers if present
    sanitized = re.sub(
        r"(api[_-]?key)=([a-zA-Z0-9_\-]+)", r"\1=***", sanitized, flags=re.IGNORECASE
    )
    return sanitized


class StructuredJSONFormatter(logging.Formatter):
    """Formatter that outputs structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_sensitive_data(record.getMessage()),
        }

        # Inject request_id if available in context or explicitly attached to record
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        if req_id:
            log_entry["request_id"] = req_id

        # Inject standard contextual HTTP / operational fields if present
        for field in ("method", "path", "status_code", "latency_ms", "error_type", "cache_hit"):
            val = getattr(record, field, None)
            if val is not None:
                log_entry[field] = val

        # Handle exception tracebacks safely
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "UnknownException",
                "message": sanitize_sensitive_data(str(record.exc_info[1])),
                "traceback": sanitize_sensitive_data(traceback.format_exc()),
            }

        return json.dumps(log_entry, default=str)


def setup_logging(level: int = getattr(logging, settings.LOG_LEVEL)) -> logging.Logger:
    """Configure structured JSON logging for the application root logger."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers if setup is called multiple times
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJSONFormatter())
    root_logger.addHandler(handler)

    # Set third-party loggers to a reasonable level to avoid noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    return logging.getLogger("app")


def get_logger(name: str) -> logging.Logger:
    """Obtain a logger instance by name."""
    return logging.getLogger(name)

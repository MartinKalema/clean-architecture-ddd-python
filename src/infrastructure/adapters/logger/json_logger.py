"""
Structured JSON Logger for production environments.

Outputs logs in JSON format for easy parsing by log aggregation tools
like ELK Stack, Datadog, Splunk, etc.
"""
import json
import logging
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from src.domain.shared_kernel import Logger


class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs JSON structured logs."""

    def __init__(self, service_name: str = "library-service"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
        }

        if hasattr(record, "extra"):
            log_entry.update(record.extra)

        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stacktrace": traceback.format_exception(*record.exc_info) if record.exc_info[0] else None
            }

        log_entry["source"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName
        }

        return json.dumps(log_entry, default=str)


class JsonLogger(Logger):
    """
    Structured JSON logger implementation.

    Outputs logs in JSON format suitable for production environments
    with centralized log management.
    """

    def __init__(
        self,
        name: str = "clean_architecture",
        service_name: str = "library-service",
        level: int = logging.INFO
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self._extra: Dict[str, Any] = {}

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JsonFormatter(service_name=service_name))
            self.logger.addHandler(handler)

    def with_context(self, **kwargs) -> "JsonLogger":
        """
        Create a new logger with additional context fields.

        Example:
            logger.with_context(request_id="123", user_id="456").info("Processing request")
        """
        new_logger = JsonLogger.__new__(JsonLogger)
        new_logger.logger = self.logger
        new_logger._extra = {**self._extra, **kwargs}
        return new_logger

    def _log(self, level: int, message: str, exception: Optional[Exception] = None) -> None:
        """Internal method to log with extra context."""
        extra = {"extra": self._extra} if self._extra else {}
        self.logger.log(level, message, exc_info=exception, extra=extra, stacklevel=3)

    def info(self, message: str) -> None:
        self._log(logging.INFO, message)

    def error(self, message: str, exception: Optional[Exception] = None) -> None:
        self._log(logging.ERROR, message, exception)

    def warning(self, message: str) -> None:
        self._log(logging.WARNING, message)

    def debug(self, message: str) -> None:
        self._log(logging.DEBUG, message)

"""
Logger Factory for creating appropriate logger instances.

Encapsulates the decision logic for which logger implementation to use
based on configuration. Keeps the container free of creation logic.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Union

from .json_logger import JsonLogger
from .standard_logger import StandardLogger

if TYPE_CHECKING:
    from src.application.ports import ILogger


class LoggerFactory:
    """
    Factory for creating logger instances based on configuration.

    Callable factory - returns Logger instance, not LoggerFactory.

    Usage in container:
        logger = providers.Singleton(LoggerFactory, config=config)
    """

    def __new__(cls, config: Dict[str, Any]) -> Union[JsonLogger, StandardLogger]:  # type: ignore[misc]
        """
        Create a logger instance based on configuration.

        Args:
            config: Application configuration dictionary containing
                   logging.format ('json' or 'standard')

        Returns:
            Logger instance (JsonLogger or StandardLogger)
        """
        log_format = config.get("logging", {}).get("format", "json")
        level_name = config.get("logging", {}).get("level", "INFO")
        level = getattr(logging, level_name, logging.INFO)

        if log_format == "json":
            return JsonLogger(level=level)
        return StandardLogger(level=level)

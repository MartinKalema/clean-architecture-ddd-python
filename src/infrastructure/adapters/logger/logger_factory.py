"""
Logger Factory for creating appropriate logger instances.

Encapsulates the decision logic for which logger implementation to use
based on configuration. Keeps the container free of creation logic.
"""
from typing import Dict, Any

from src.domain.shared_kernel import Logger
from .json_logger import JsonLogger
from .standard_logger import StandardLogger


class LoggerFactory:
    """
    Factory for creating logger instances based on configuration.

    Usage in container:
        logger = providers.Singleton(LoggerFactory.create, config=config)
    """

    @staticmethod
    def create(config: Dict[str, Any]) -> Logger:
        """
        Create a logger instance based on configuration.

        Args:
            config: Application configuration dictionary containing
                   logging.format ('json' or 'standard')

        Returns:
            Logger instance (JsonLogger or StandardLogger)
        """
        log_format = config.get("logging", {}).get("format", "json")

        if log_format == "json":
            return JsonLogger()
        return StandardLogger()

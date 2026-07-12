"""
etcd Adapter - Real-time configuration from etcd.

This adapter loads configuration from etcd and supports real-time
updates via etcd's watch mechanism.
"""
from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from src.infrastructure.external.etcd_client import EtcdClient

if TYPE_CHECKING:
    from src.application.ports import ILogger


class EtcdAdapter:
    """
    Adapter that loads config from etcd.

    Features:
    - Loads configuration from etcd key-value store
    - Supports real-time updates via watch
    - Thread-safe configuration access
    - Hierarchical key structure (e.g., /config/database/url)
    """

    def __init__(
        self,
        client: EtcdClient,
        config_prefix: str = "/config/",
        logger: Optional[ILogger] = None,
    ):
        self._client = client
        self._config_prefix = config_prefix
        self._logger = logger
        self._config: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._watch_id: Optional[int] = None
        self._change_callbacks: list[Callable[[str, Any], None]] = []

    def load(self) -> None:
        """Load all configuration from etcd."""
        self._client.connect()
        raw_config = self._client.get_prefix(self._config_prefix)

        with self._lock:
            self._config = self._parse_config(raw_config)

        if self._logger:
            self._logger.info(f"Loaded {len(raw_config)} config keys from etcd")

    def _parse_config(self, raw_config: Dict[str, str]) -> Dict[str, Any]:
        """
        Parse raw etcd key-value pairs into nested config structure.

        Converts:
          /config/database/url -> {"database": {"url": ...}}
        """
        config: Dict[str, Any] = {}

        for key, value in raw_config.items():
            key_path = key.replace(self._config_prefix, "").strip("/")
            parts = key_path.split("/")

            try:
                parsed_value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed_value = value

            current = config
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            if parts:
                current[parts[-1]] = parsed_value

        return config

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by dot-notation key.

        Example: get("database.url") returns config["database"]["url"]
        """
        with self._lock:
            parts = key.split(".")
            current = self._config

            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return default

            return current

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration as a dictionary."""
        with self._lock:
            return self._config.copy()

    def watch(self, key: str, callback: Callable[[Any], None]) -> None:
        """
        Watch a specific key for changes.

        The callback is called with the new value when the key changes.
        """
        full_key = f"{self._config_prefix}{key.replace('.', '/')}"
        self._client.watch(full_key, callback)

    def start_watching(self) -> None:
        """
        Start watching all config keys for changes.

        When any config key changes, the internal config is updated
        and all registered callbacks are notified.
        """
        def on_change(key: str, value: str) -> None:
            key_path = key.replace(self._config_prefix, "").strip("/")
            parts = key_path.split("/")

            try:
                parsed_value = json.loads(value) if value else None
            except (json.JSONDecodeError, TypeError):
                parsed_value = value

            with self._lock:
                current = self._config
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

                if parts:
                    current[parts[-1]] = parsed_value

            dot_key = ".".join(parts)
            if self._logger:
                self._logger.info(f"Config changed: {dot_key}")

            for callback in self._change_callbacks:
                try:
                    callback(dot_key, parsed_value)
                except Exception as e:
                    if self._logger:
                        self._logger.error(f"Error in config change callback: {e}")

        self._watch_id = self._client.watch_prefix(self._config_prefix, on_change)

        if self._logger:
            self._logger.info("Started watching for config changes")

    def stop_watching(self) -> None:
        """Stop watching for config changes."""
        if self._watch_id is not None:
            self._client.cancel_watch(self._watch_id)
            self._watch_id = None

            if self._logger:
                self._logger.info("Stopped watching for config changes")

    def on_change(self, callback: Callable[[str, Any], None]) -> None:
        """
        Register a callback to be called when any config changes.

        The callback receives (key, new_value) where key is in dot notation.
        """
        self._change_callbacks.append(callback)

    def close(self) -> None:
        """Close the provider and release resources."""
        self.stop_watching()
        self._client.close()

    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value (writes to etcd).

        This is useful for programmatic config updates.
        """
        full_key = f"{self._config_prefix}{key.replace('.', '/')}"
        json_value = json.dumps(value) if not isinstance(value, str) else value
        self._client.put(full_key, json_value)

        if self._logger:
            self._logger.debug(f"Set config: {key}")

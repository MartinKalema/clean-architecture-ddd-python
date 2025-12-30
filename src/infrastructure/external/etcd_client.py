"""
etcd Client - External service wrapper for etcd.

This is a thin wrapper around the etcd3 library that handles
connection management and provides a clean interface.
"""
import threading
from typing import Any, Callable, Optional

import etcd3

from src.domain.shared_kernel import Logger


class EtcdClient:
    """
    Client for connecting to etcd.

    Handles connection lifecycle and provides methods for
    key-value operations and watching for changes.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 2379,
        logger: Optional[Logger] = None,
    ):
        self._host = host
        self._port = port
        self._logger = logger
        self._client: Optional[etcd3.Etcd3Client] = None
        self._watch_callbacks: dict[int, Callable] = {}
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Establish connection to etcd."""
        if self._client is None:
            self._client = etcd3.client(host=self._host, port=self._port)
            if self._logger:
                self._logger.info(f"Connected to etcd at {self._host}:{self._port}")

    def close(self) -> None:
        """Close the connection to etcd."""
        if self._client:
            self._client.close()
            self._client = None
            if self._logger:
                self._logger.info("Disconnected from etcd")

    def _ensure_connected(self) -> etcd3.Etcd3Client:
        """Ensure we have an active connection."""
        if self._client is None:
            self.connect()
        return self._client  # type: ignore

    def get(self, key: str) -> Optional[bytes]:
        """Get a value by key."""
        client = self._ensure_connected()
        value, _ = client.get(key)
        return value

    def get_string(self, key: str) -> Optional[str]:
        """Get a value as string."""
        value = self.get(key)
        return value.decode("utf-8") if value else None

    def put(self, key: str, value: str) -> None:
        """Set a value for a key."""
        client = self._ensure_connected()
        client.put(key, value)
        if self._logger:
            self._logger.debug(f"Set etcd key: {key}")

    def delete(self, key: str) -> bool:
        """Delete a key."""
        client = self._ensure_connected()
        deleted = client.delete(key)
        return deleted

    def get_prefix(self, prefix: str) -> dict[str, str]:
        """Get all keys with a given prefix."""
        client = self._ensure_connected()
        result = {}
        for value, metadata in client.get_prefix(prefix):
            key = metadata.key.decode("utf-8")
            result[key] = value.decode("utf-8") if value else ""
        return result

    def watch(self, key: str, callback: Callable[[Any], None]) -> int:
        """
        Watch a key for changes.

        Returns a watch_id that can be used to cancel the watch.
        The callback receives the new value when the key changes.
        """
        client = self._ensure_connected()

        def watch_callback(event: Any) -> None:
            for ev in event.events:
                new_value = ev.value.decode("utf-8") if ev.value else None
                callback(new_value)

        watch_id = client.add_watch_callback(key, watch_callback)

        with self._lock:
            self._watch_callbacks[watch_id] = callback

        if self._logger:
            self._logger.info(f"Started watching etcd key: {key}")

        return watch_id

    def watch_prefix(self, prefix: str, callback: Callable[[str, Any], None]) -> int:
        """
        Watch all keys with a given prefix for changes.

        Returns a watch_id that can be used to cancel the watch.
        The callback receives (key, new_value) when any key changes.
        """
        client = self._ensure_connected()

        def watch_callback(event: Any) -> None:
            for ev in event.events:
                key = ev.key.decode("utf-8")
                new_value = ev.value.decode("utf-8") if ev.value else None
                callback(key, new_value)

        watch_id = client.add_watch_prefix_callback(prefix, watch_callback)

        with self._lock:
            self._watch_callbacks[watch_id] = callback

        if self._logger:
            self._logger.info(f"Started watching etcd prefix: {prefix}")

        return watch_id

    def cancel_watch(self, watch_id: int) -> None:
        """Cancel a watch by its ID."""
        client = self._ensure_connected()
        client.cancel_watch(watch_id)

        with self._lock:
            self._watch_callbacks.pop(watch_id, None)

        if self._logger:
            self._logger.debug(f"Cancelled watch: {watch_id}")

    @property
    def is_connected(self) -> bool:
        """Check if connected to etcd."""
        return self._client is not None

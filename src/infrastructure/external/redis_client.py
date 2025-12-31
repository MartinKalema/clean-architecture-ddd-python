"""
Redis Client - External service wrapper for Redis caching.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

import redis

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class RedisClient:
    """
    Client for Redis caching operations.

    Provides sync caching with JSON serialization.
    Configuration is loaded from etcd via dependency injection.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        default_ttl: int = 300,
        enabled: bool = True,
        logger: Optional[ILogger] = None,
    ):
        self._url = url
        self._default_ttl = default_ttl
        self._enabled = enabled
        self._logger = logger
        self._client: Optional[redis.Redis] = None

    def connect(self) -> None:
        """Establish connection to Redis."""
        if not self._enabled:
            if self._logger:
                self._logger.info("Redis caching is disabled")
            return

        if self._client is None:
            self._client = redis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            if self._logger:
                self._logger.info(f"Connected to Redis at {self._url}")

    def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            self._client.close()
            self._client = None
            if self._logger:
                self._logger.info("Disconnected from Redis")

    def _ensure_connected(self) -> Optional[redis.Redis]:
        """Ensure we have an active connection."""
        if not self._enabled:
            return None
        if self._client is None:
            self.connect()
        return self._client

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache, returns None if not found or disabled."""
        client = self._ensure_connected()
        if not client:
            return None

        try:
            value = client.get(key)
            if value:
                return json.loads(value)
            return None
        except (redis.RedisError, json.JSONDecodeError) as e:
            if self._logger:
                self._logger.warning(f"Redis get error for {key}: {e}")
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in cache with optional TTL."""
        client = self._ensure_connected()
        if not client:
            return False

        try:
            serialized = json.dumps(value, default=str)
            client.setex(key, ttl or self._default_ttl, serialized)
            return True
        except (redis.RedisError, TypeError) as e:
            if self._logger:
                self._logger.warning(f"Redis set error for {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        client = self._ensure_connected()
        if not client:
            return False

        try:
            client.delete(key)
            return True
        except redis.RedisError as e:
            if self._logger:
                self._logger.warning(f"Redis delete error for {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern."""
        client = self._ensure_connected()
        if not client:
            return 0

        try:
            keys = list(client.scan_iter(match=pattern, count=1000))
            if keys:
                return client.delete(*keys)
            return 0
        except redis.RedisError as e:
            if self._logger:
                self._logger.warning(f"Redis delete_pattern error for {pattern}: {e}")
            return 0

    def invalidate_entity(self, entity_type: str, entity_id: str) -> None:
        """Invalidate all cache entries for a specific entity."""
        self.delete(f"{entity_type}:{entity_id}")
        self.delete_pattern(f"{entity_type}:list:*")
        self.delete_pattern(f"{entity_type}:count:*")

    def invalidate_all(self, entity_type: str) -> None:
        """Invalidate all cache entries for an entity type."""
        self.delete_pattern(f"{entity_type}:*")

    @property
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._enabled

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        if not self._enabled:
            return False
        client = self._ensure_connected()
        if not client:
            return False
        try:
            client.ping()
            return True
        except redis.RedisError:
            return False

"""
Cache Adapter - Application layer cache interface.

This adapter provides caching capabilities to command and query handlers.
It wraps the RedisClient and provides a clean interface for the application layer.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, TypeVar

if TYPE_CHECKING:
    from src.infrastructure.external.redis_client import RedisClient

T = TypeVar("T")


class CacheAdapter:
    """
    Async cache adapter for application layer handlers.

    Provides:
    - Simple get/set operations
    - Cache-aside pattern helpers
    - Entity-based invalidation
    """

    def __init__(self, client: RedisClient):
        self._client = client

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache."""
        return await self._client.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in cache."""
        return await self._client.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        return await self._client.delete(key)

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        ttl: Optional[int] = None,
    ) -> T:
        """
        Get from cache or compute and cache the value.

        This implements the cache-aside pattern:
        1. Check cache for key
        2. If found, return cached value
        3. If not found, call factory to compute value
        4. Cache the computed value
        5. Return the value
        """
        cached = await self._client.get(key)
        if cached is not None:
            return cached

        result = await factory()

        if result is not None:
            await self._client.set(key, result, ttl)

        return result

    async def invalidate_entity(self, entity_type: str, entity_id: str) -> None:
        """
        Invalidate cache for a specific entity.

        Removes:
        - The entity's direct cache key
        - All list caches for this entity type
        - All count caches for this entity type
        """
        await self._client.invalidate_entity(entity_type, entity_id)

    async def invalidate_all(self, entity_type: str) -> None:
        """Invalidate all cache entries for an entity type."""
        await self._client.invalidate_all(entity_type)

    @property
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._client.is_enabled

    def build_key(self, *parts: Any) -> str:
        """Build a cache key from parts."""
        return ":".join(str(p) for p in parts)

    def build_list_key(self, entity_type: str, **filters: Any) -> str:
        """Build a cache key for list queries."""
        filter_str = ":".join(f"{k}={v}" for k, v in sorted(filters.items()))
        return f"{entity_type}:list:{filter_str}"

    def build_count_key(self, entity_type: str, **filters: Any) -> str:
        """Build a cache key for count queries."""
        filter_str = ":".join(f"{k}={v}" for k, v in sorted(filters.items()))
        return f"{entity_type}:count:{filter_str}"

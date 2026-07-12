"""
Cache Adapter - Application layer cache interface.

This adapter provides caching capabilities to command and query handlers.
It wraps the RedisClient and provides a clean interface for the application layer.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import weakref
from datetime import datetime
from enum import Enum
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
        self._local_flights: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        # A generation increment is the correctness fence for a committed
        # write. If Redis cannot persist it, this process must not read or
        # populate the old generation. A bounded-backoff recovery task keeps
        # retrying the global increment; once it succeeds every replica moves
        # past the stale generation.
        self._unsafe_namespaces: set[str] = set()
        self._recovery_locks: dict[str, asyncio.Lock] = {}
        self._recovery_tasks: dict[str, asyncio.Task[None]] = {}

    KEY_VERSION = "v1"
    LOCK_TTL_SECONDS = 60.0
    LOCK_WAIT_SECONDS = 2.0
    RECOVERY_INITIAL_DELAY_SECONDS = 0.1
    RECOVERY_MAX_DELAY_SECONDS = 5.0

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
        namespace = self._key_namespace(key)
        if namespace in self._unsafe_namespaces:
            # Try once on the request path to shorten recovery, but never
            # consult or refill Redis until a global generation increment has
            # definitely succeeded.
            if not await self._recover_namespace_once(namespace):
                return await factory()
        generation = await self._client.get_namespace_generation(namespace)
        if generation is None:
            return await factory()
        versioned_key = self._generation_key(key, generation)
        cached = await self._client.get(versioned_key)
        if cached is not None:
            return cached

        # Collapse concurrent misses inside a process, then use a short Redis
        # lease to collapse misses across API replicas. Locks are weakly held
        # so attacker-controlled, one-off query keys cannot grow this map.
        flight = self._local_flights.get(versioned_key)
        if flight is None:
            flight = asyncio.Lock()
            self._local_flights[versioned_key] = flight

        async with flight:
            generation = await self._client.get_namespace_generation(namespace)
            if generation is None:
                return await factory()
            versioned_key = self._generation_key(key, generation)
            cached = await self._client.get(versioned_key)
            if cached is not None:
                return cached

            lock_key = self._lock_key(versioned_key)
            token = await self._client.try_acquire_lock(
                lock_key, ttl_seconds=self.LOCK_TTL_SECONDS
            )
            if token is False:
                cached = await self._wait_for_peer(versioned_key)
                if cached is not None:
                    return cached
                token = await self._client.try_acquire_lock(
                    lock_key, ttl_seconds=self.LOCK_TTL_SECONDS
                )

            try:
                result = await factory()
                current_generation = await self._client.get_namespace_generation(
                    namespace
                )
                if current_generation is None:
                    # Redis lost the generation read while the source query
                    # was running. Return the authoritative value without
                    # populating a generation we can no longer prove current.
                    return result
                if current_generation != generation:
                    # The factory may have observed state from before a write
                    # that committed while it was running. Re-read once under
                    # the new generation and never populate the stale key.
                    result = await factory()
                    generation = current_generation
                    versioned_key = self._generation_key(key, generation)
                if result is not None:
                    await self._client.set(versioned_key, result, ttl)
                return result
            finally:
                if isinstance(token, str):
                    await self._client.release_lock(lock_key, token)

    async def invalidate_entity(self, entity_type: str, entity_id: str) -> bool:
        """
        Invalidate cache for a specific entity.

        Removes:
        - The entity's direct cache key
        - All list caches for this entity type
        - All count caches for this entity type
        """
        namespace = self._namespace(entity_type)
        fenced = await self._advance_generation(namespace)
        await self._client.delete(self.build_key(namespace, entity_id))
        await self._client.delete_pattern(f"{namespace}:list:{self.KEY_VERSION}:*")
        await self._client.delete_pattern(f"{namespace}:count:{self.KEY_VERSION}:*")
        return fenced

    async def invalidate_all(self, entity_type: str) -> bool:
        """Invalidate all cache entries for an entity type."""
        namespace = self._namespace(entity_type)
        fenced = await self._advance_generation(namespace)
        await self._client.delete_pattern(f"{namespace}:*:{self.KEY_VERSION}:*")
        return fenced

    async def _advance_generation(self, namespace: str) -> bool:
        """Persist the authoritative cache fence or enter fail-closed mode."""
        generation = await self._client.bump_namespace_generation(namespace)
        if generation is not None or not self._client.is_enabled:
            self._unsafe_namespaces.discard(namespace)
            return True
        self._unsafe_namespaces.add(namespace)
        self._start_recovery(namespace)
        return False

    def _start_recovery(self, namespace: str) -> None:
        task = self._recovery_tasks.get(namespace)
        if task is not None and not task.done():
            return
        self._recovery_tasks[namespace] = asyncio.create_task(
            self._recover_namespace(namespace),
            name=f"cache-generation-recovery:{namespace}",
        )

    async def _recover_namespace(self, namespace: str) -> None:
        delay = self.RECOVERY_INITIAL_DELAY_SECONDS
        try:
            while namespace in self._unsafe_namespaces:
                await asyncio.sleep(delay)
                if await self._recover_namespace_once(namespace):
                    return
                delay = min(delay * 2, self.RECOVERY_MAX_DELAY_SECONDS)
        finally:
            current = asyncio.current_task()
            if self._recovery_tasks.get(namespace) is current:
                self._recovery_tasks.pop(namespace, None)

    async def _recover_namespace_once(self, namespace: str) -> bool:
        if namespace not in self._unsafe_namespaces:
            return True
        lock = self._recovery_locks.setdefault(namespace, asyncio.Lock())
        async with lock:
            if namespace not in self._unsafe_namespaces:
                return True
            generation = await self._client.bump_namespace_generation(namespace)
            if generation is None:
                return False
            self._unsafe_namespaces.discard(namespace)
            return True

    @property
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._client.is_enabled

    def build_key(self, *parts: Any) -> str:
        """Build a bounded key that does not expose IDs or user input."""
        if not parts:
            raise ValueError("at least one cache-key part is required")
        namespace = self._namespace(str(parts[0]))
        return self._hashed_key(namespace, "item", list(parts[1:]))

    def build_list_key(self, entity_type: str, **filters: Any) -> str:
        """Build a cache key for list queries."""
        return self._hashed_key(self._namespace(entity_type), "list", filters)

    def build_count_key(self, entity_type: str, **filters: Any) -> str:
        """Build a cache key for count queries."""
        return self._hashed_key(self._namespace(entity_type), "count", filters)

    async def _wait_for_peer(self, key: str) -> Any | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.LOCK_WAIT_SECONDS
        delay = 0.025
        while loop.time() < deadline:
            await asyncio.sleep(delay)
            cached = await self._client.get(key)
            if cached is not None:
                return cached
            delay = min(delay * 2, 0.2)
        return None

    @classmethod
    def _namespace(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value):
            raise ValueError("invalid cache namespace")
        return value

    @classmethod
    def _hashed_key(cls, namespace: str, kind: str, value: Any) -> str:
        canonical = json.dumps(
            value,
            default=_canonical_default,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{namespace}:{kind}:{cls.KEY_VERSION}:{digest}"

    @staticmethod
    def _lock_key(key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"cache-lock:v1:{digest}"

    @classmethod
    def _key_namespace(cls, key: str) -> str:
        namespace, separator, _rest = key.partition(":")
        if not separator:
            raise ValueError("cache key must start with a namespace")
        return cls._namespace(namespace)

    @staticmethod
    def _generation_key(key: str, generation: int) -> str:
        return f"{key}:g{generation}"


def _canonical_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported cache key value: {type(value).__name__}")

"""
Redis Client - External service wrapper for Redis caching.
"""
from __future__ import annotations

import json
import random
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlsplit, urlunsplit

import redis.asyncio as redis

if TYPE_CHECKING:
    from src.application.ports import ILogger


class RedisClient:
    """
    Async client for Redis caching operations.

    Provides async caching with JSON serialization.
    Configuration is loaded from etcd via dependency injection.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        default_ttl: int = 120,
        enabled: bool = True,
        ttl_jitter_ratio: float = 0.10,
        logger: Optional[ILogger] = None,
    ):
        self._url = url
        self._default_ttl = default_ttl
        self._enabled = enabled
        self._ttl_jitter_ratio = min(max(ttl_jitter_ratio, 0.0), 0.5)
        self._logger = logger
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
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
                # Never emit URI user-info or query parameters: Redis URLs
                # commonly carry production credentials.
                self._logger.info(
                    f"Connected to Redis at {safe_redis_endpoint(self._url)}"
                )

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            if self._logger:
                self._logger.info("Disconnected from Redis")

    async def _ensure_connected(self) -> Optional[redis.Redis]:
        """Ensure we have an active connection."""
        if not self._enabled:
            return None
        if self._client is None:
            await self.connect()
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache, returns None if not found or disabled."""
        client = await self._ensure_connected()
        if not client:
            return None

        try:
            value = await client.get(key)
            if value:
                return json.loads(value, object_hook=_json_object_hook)
            return None
        except (redis.RedisError, json.JSONDecodeError) as e:
            if self._logger:
                self._logger.warning(f"Redis get error for {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in cache with optional TTL."""
        client = await self._ensure_connected()
        if not client:
            return False

        try:
            serialized = json.dumps(value, default=_json_default)
            effective_ttl = self._effective_ttl(
                self._default_ttl if ttl is None else ttl
            )
            await client.setex(key, effective_ttl, serialized)
            return True
        except (redis.RedisError, TypeError) as e:
            if self._logger:
                self._logger.warning(f"Redis set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        client = await self._ensure_connected()
        if not client:
            return False

        try:
            await client.delete(key)
            return True
        except redis.RedisError as e:
            if self._logger:
                self._logger.warning(f"Redis delete error for {key}: {e}")
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete matching keys incrementally without materializing the keyspace."""
        client = await self._ensure_connected()
        if not client:
            return 0

        try:
            deleted = 0
            batch: list[str] = []
            async for key in client.scan_iter(match=pattern, count=500):
                batch.append(key)
                if len(batch) == 500:
                    deleted += int(await client.unlink(*batch))
                    batch.clear()
            if batch:
                deleted += int(await client.unlink(*batch))
            return deleted
        except redis.RedisError as e:
            if self._logger:
                self._logger.warning(f"Redis delete_pattern error for {pattern}: {e}")
            return 0

    async def get_namespace_generation(self, namespace: str) -> int | None:
        """Return the cross-replica cache generation for one read namespace."""
        client = await self._ensure_connected()
        if not client:
            return 0
        try:
            raw = await client.get(f"cache-generation:v1:{namespace}")
            return int(raw) if raw is not None else 0
        except (redis.RedisError, TypeError, ValueError) as error:
            if self._logger:
                self._logger.warning(
                    f"Redis generation read error for {namespace}: {error}"
                )
            # Zero is a valid generation. Returning it on an operational
            # failure could make a stale pre-write entry reachable again.
            return None

    async def bump_namespace_generation(self, namespace: str) -> int | None:
        """Atomically fence in-flight reads started before a committed write."""
        client = await self._ensure_connected()
        if not client:
            return None
        try:
            return int(await client.incr(f"cache-generation:v1:{namespace}"))
        except redis.RedisError as error:
            if self._logger:
                self._logger.warning(
                    f"Redis generation increment error for {namespace}: {error}"
                )
            return None

    async def invalidate_entity(self, entity_type: str, entity_id: str) -> None:
        """Invalidate all cache entries for a specific entity."""
        await self.delete(f"{entity_type}:{entity_id}")
        await self.delete_pattern(f"{entity_type}:list:*")
        await self.delete_pattern(f"{entity_type}:count:*")

    async def invalidate_all(self, entity_type: str) -> None:
        """Invalidate all cache entries for an entity type."""
        await self.delete_pattern(f"{entity_type}:*")

    async def try_acquire_lock(
        self, key: str, *, ttl_seconds: float = 30.0
    ) -> str | bool | None:
        """Return a token, ``False`` on contention, or ``None`` if unavailable."""
        client = await self._ensure_connected()
        if not client:
            return None
        token = secrets.token_urlsafe(18)
        try:
            acquired = await client.set(
                key,
                token,
                nx=True,
                px=max(1, int(ttl_seconds * 1_000)),
            )
            return token if acquired else False
        except redis.RedisError as e:
            if self._logger:
                self._logger.warning(f"Redis lock error for {key}: {e}")
            return None

    async def release_lock(self, key: str, token: str) -> None:
        """Release only a lease still owned by this caller."""
        client = await self._ensure_connected()
        if not client:
            return
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            await client.eval(script, 1, key, token)
        except redis.RedisError as e:
            if self._logger:
                self._logger.warning(f"Redis unlock error for {key}: {e}")

    @property
    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self._enabled

    async def ping(self) -> bool:
        """Check if connected to Redis."""
        if not self._enabled:
            return False
        client = await self._ensure_connected()
        if not client:
            return False
        try:
            await client.ping()
            return True
        except redis.RedisError:
            return False

    def _effective_ttl(self, ttl: int) -> int:
        if ttl < 1:
            raise ValueError("cache TTL must be positive")
        spread = ttl * self._ttl_jitter_ratio
        return max(1, round(ttl + random.uniform(-spread, spread)))


_DATETIME_TYPE_KEY = "__clean_architecture_type__"


def _json_default(value: Any) -> dict[str, str]:
    if isinstance(value, datetime):
        return {_DATETIME_TYPE_KEY: "datetime", "value": value.isoformat()}
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_object_hook(value: dict[str, Any]) -> Any:
    if value.get(_DATETIME_TYPE_KEY) == "datetime" and set(value) == {
        _DATETIME_TYPE_KEY,
        "value",
    }:
        try:
            return datetime.fromisoformat(str(value["value"]).replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


def safe_redis_endpoint(url: str) -> str:
    """Return a log-safe endpoint with credentials/query/fragment removed."""
    parsed = urlsplit(url)
    hostname = parsed.hostname or "<unknown>"
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        port = ""
    # The path is only the logical database number for redis:// URLs.
    path = parsed.path if parsed.path.startswith("/") else ""
    return urlunsplit((parsed.scheme or "redis", f"{hostname}{port}", path, "", ""))

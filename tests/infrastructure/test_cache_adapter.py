import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.adapters.cache.cache_adapter import CacheAdapter
from src.infrastructure.external.redis_client import RedisClient, safe_redis_endpoint


class FakeCacheClient:
    def __init__(self):
        self.values = {}
        self.is_enabled = True
        self.deleted = []
        self.patterns = []
        self.lock_token = None
        self.generations = {}
        self.generation_reads_available = True
        self.generation_writes_available = True

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ttl=None):
        self.values[key] = value
        return True

    async def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)
        return True

    async def delete_pattern(self, pattern):
        self.patterns.append(pattern)
        return 0

    async def try_acquire_lock(self, key, ttl_seconds=30):
        if self.lock_token is not None:
            return False
        self.lock_token = "owner"
        return self.lock_token

    async def release_lock(self, key, token):
        if token == self.lock_token:
            self.lock_token = None

    async def get_namespace_generation(self, namespace):
        if not self.generation_reads_available:
            return None
        return self.generations.get(namespace, 0)

    async def bump_namespace_generation(self, namespace):
        if not self.generation_writes_available:
            return None
        generation = self.generations.get(namespace, 0) + 1
        self.generations[namespace] = generation
        return generation


def test_cache_keys_are_bounded_deterministic_and_do_not_leak_inputs():
    cache = CacheAdapter(FakeCacheClient())
    sensitive = "patron@example.test:" + "x" * 5_000

    first = cache.build_list_key("loan", patron_id=sensitive, offset=0)
    second = cache.build_list_key("loan", offset=0, patron_id=sensitive)

    assert first == second
    assert sensitive not in first
    assert len(first) < 100


@pytest.mark.asyncio
async def test_get_or_set_collapses_concurrent_misses():
    cache = CacheAdapter(FakeCacheClient())
    calls = 0

    async def factory():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"value": 42}

    results = await asyncio.gather(*(
        cache.get_or_set("book:item:v2:key", factory) for _ in range(20)
    ))

    assert calls == 1
    assert results == [{"value": 42}] * 20


@pytest.mark.asyncio
async def test_entity_invalidation_uses_hashed_item_and_bounded_patterns():
    client = FakeCacheClient()
    cache = CacheAdapter(client)

    await cache.invalidate_entity("book", "secret-book-id")

    assert "secret-book-id" not in client.deleted[0]
    assert client.patterns == ["book:list:v2:*", "book:count:v2:*"]
    assert client.generations["book"] == 1


@pytest.mark.asyncio
async def test_write_generation_prevents_inflight_stale_cache_population():
    client = FakeCacheClient()
    cache = CacheAdapter(client)
    started = asyncio.Event()
    release = asyncio.Event()
    values = iter(["old", "current"])

    async def factory():
        started.set()
        await release.wait()
        return next(values)

    read = asyncio.create_task(
        cache.get_or_set("book:item:v2:key", factory)
    )
    await started.wait()
    await cache.invalidate_all("book")
    release.set()

    assert await read == "current"
    assert "old" not in client.values.values()
    assert client.values["book:item:v2:key:g1"] == "current"


@pytest.mark.asyncio
async def test_failed_write_fence_bypasses_stale_generation_until_recovery():
    client = FakeCacheClient()
    cache = CacheAdapter(client)
    cache.RECOVERY_INITIAL_DELAY_SECONDS = 0.01
    key = "book:item:v2:key"
    client.values[f"{key}:g0"] = "stale"
    client.generation_writes_available = False

    assert await cache.invalidate_all("book") is False
    assert "book" in cache._unsafe_namespaces
    assert await cache.get_or_set(key, AsyncMock(return_value="database")) == "database"
    assert client.values[f"{key}:g0"] == "stale"

    client.generation_writes_available = True
    factory = AsyncMock(return_value="current")
    assert await cache.get_or_set(key, factory) == "current"
    assert client.generations["book"] >= 1
    assert "book" not in cache._unsafe_namespaces
    assert "current" in client.values.values()

    recovery = cache._recovery_tasks.get("book")
    if recovery is not None:
        await asyncio.wait_for(recovery, timeout=1)


@pytest.mark.asyncio
async def test_generation_read_failure_bypasses_cache_without_refilling_it():
    client = FakeCacheClient()
    cache = CacheAdapter(client)
    key = "book:item:v2:key"
    client.values[f"{key}:g0"] = "stale"
    client.generation_reads_available = False
    factory = AsyncMock(return_value="database")

    assert await cache.get_or_set(key, factory) == "database"
    factory.assert_awaited_once()
    assert list(client.values.values()) == ["stale"]


def test_safe_redis_endpoint_redacts_all_credentials_and_query_data():
    endpoint = safe_redis_endpoint(
        "rediss://service-user:s3cr3t@[2001:db8::1]:6380/4?ssl_cert_reqs=none"
    )

    assert endpoint == "rediss://[2001:db8::1]:6380/4"
    assert "service-user" not in endpoint
    assert "s3cr3t" not in endpoint
    assert "ssl_cert_reqs" not in endpoint


@pytest.mark.asyncio
async def test_connect_log_uses_only_safe_redis_endpoint():
    logger = MagicMock()
    client = RedisClient(
        url="redis://user:password@redis.internal:6379/3?token=secret",
        logger=logger,
    )

    with patch("src.infrastructure.external.redis_client.redis.from_url", return_value=MagicMock()):
        await client.connect()

    message = logger.info.call_args.args[0]
    assert message == "Connected to Redis at redis://redis.internal:6379/3"


@pytest.mark.asyncio
async def test_redis_codec_round_trips_datetime_as_datetime():
    fake = MagicMock()
    fake.setex = AsyncMock()
    client = RedisClient(ttl_jitter_ratio=0)
    client._client = fake
    timestamp = datetime(2026, 7, 11, 10, tzinfo=timezone.utc)

    await client.set("key", {"when": timestamp}, ttl=60)
    serialized = fake.setex.await_args.args[2]
    fake.get = AsyncMock(return_value=serialized)

    value = await client.get("key")

    assert value == {"when": timestamp}
    fake.setex.assert_awaited_once_with("key", 60, serialized)


@pytest.mark.asyncio
async def test_pattern_deletion_unlinks_in_bounded_batches():
    fake = MagicMock()

    async def scan_iter(**kwargs):
        for index in range(1_201):
            yield f"key-{index}"

    fake.scan_iter = scan_iter
    fake.unlink = AsyncMock(side_effect=lambda *keys: len(keys))
    client = RedisClient()
    client._client = fake

    deleted = await client.delete_pattern("book:list:v2:*")

    assert deleted == 1_201
    assert [len(call.args) for call in fake.unlink.await_args_list] == [500, 500, 201]

"""Write handlers invalidate read caches only after successful completion."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.cache_invalidation import CacheInvalidatingHandler


@pytest.mark.asyncio
async def test_invalidates_namespace_after_successful_command():
    inner = AsyncMock()
    inner.handle.return_value = {"id": "book-1"}
    cache = AsyncMock()
    handler = CacheInvalidatingHandler(inner, cache, "book")

    result = await handler.handle(object())

    assert result == {"id": "book-1"}
    cache.invalidate_all.assert_awaited_once_with("book")


@pytest.mark.asyncio
async def test_does_not_invalidate_when_command_did_not_commit():
    inner = AsyncMock()
    inner.handle.side_effect = RuntimeError("database down")
    cache = AsyncMock()
    handler = CacheInvalidatingHandler(inner, cache, "book")

    with pytest.raises(RuntimeError, match="database down"):
        await handler.handle(object())

    cache.invalidate_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_failure_cannot_turn_a_committed_command_into_an_error():
    inner = AsyncMock()
    inner.handle.return_value = {"id": "book-1"}
    cache = AsyncMock()
    cache.invalidate_all.side_effect = RuntimeError("redis unavailable")
    logger = MagicMock()
    handler = CacheInvalidatingHandler(
        inner,
        cache,
        "book",
        logger=logger,
    )

    assert await handler.handle(object()) == {"id": "book-1"}
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_failed_generation_fence_is_observable_without_failing_command():
    inner = AsyncMock()
    inner.handle.return_value = {"id": "book-1"}
    cache = AsyncMock()
    cache.invalidate_all.return_value = False
    logger = MagicMock()
    handler = CacheInvalidatingHandler(
        inner,
        cache,
        "book",
        logger=logger,
    )

    assert await handler.handle(object()) == {"id": "book-1"}
    assert "fence is recovering" in logger.warning.call_args.args[0]

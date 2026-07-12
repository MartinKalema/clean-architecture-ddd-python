"""Reservation reaping commits and invalidates one bounded batch at a time."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.run_reservation_reaper import release_all_expired
from src.application.cache_invalidation import CacheInvalidatingHandler
from src.application.command_handlers.release_expired_reservations import (
    ReleaseExpiredReservationsCommand,
    ReleaseExpiredReservationsHandler,
    ReleaseExpiredReservationsResult,
)


class _Clock:
    def now(self):
        return datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


def _book(index: int):
    book = MagicMock()
    book.id.value = f"book-{index}"
    book.title.value = f"Book {index}"
    book.reservation_id.value = (
        f"00000000-0000-4000-8000-{index:012d}"
    )
    book.reservation_generation = index
    book.reserved_patron_id = f"patron-{index}"
    book.release.return_value = True
    return book


def _uow(expired):
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.books = AsyncMock()
    uow.books.find_expired_reservations.return_value = expired
    uow.borrow_operations = AsyncMock()
    uow.commit = AsyncMock()
    return uow


@pytest.mark.asyncio
async def test_handler_commits_at_most_one_bounded_batch():
    first_batch = [_book(1), _book(2)]
    uow = _uow(first_batch)
    # A second value exposes an accidental handler-level drain loop.
    uow.books.find_expired_reservations.side_effect = [first_batch, [_book(3)]]
    handler = ReleaseExpiredReservationsHandler(
        uow=uow,
        logger=MagicMock(),
        clock=_Clock(),
    )

    result = await handler.handle(
        ReleaseExpiredReservationsCommand(ttl_seconds=300, batch_size=2)
    )

    assert result == ReleaseExpiredReservationsResult(
        released_count=2,
        batch_full=True,
    )
    uow.books.find_expired_reservations.assert_awaited_once()
    uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_crosses_cache_decorator_after_every_committed_batch():
    cache = AsyncMock()
    first = AsyncMock()
    first.handle.return_value = ReleaseExpiredReservationsResult(2, True)
    second = AsyncMock()
    second.handle.return_value = ReleaseExpiredReservationsResult(1, False)
    handlers = [
        CacheInvalidatingHandler(first, cache, "book"),
        CacheInvalidatingHandler(second, cache, "book"),
    ]

    total = await release_all_expired(
        lambda: handlers.pop(0),
        ReleaseExpiredReservationsCommand(ttl_seconds=300, batch_size=2),
    )

    assert total == 3
    assert cache.invalidate_all.await_count == 2
    cache.invalidate_all.assert_awaited_with("book")


@pytest.mark.asyncio
async def test_later_batch_failure_cannot_skip_prior_batch_invalidation():
    cache = AsyncMock()
    committed = AsyncMock()
    committed.handle.return_value = ReleaseExpiredReservationsResult(2, True)
    failing = AsyncMock()
    failing.handle.side_effect = RuntimeError("database down")
    handlers = [
        CacheInvalidatingHandler(committed, cache, "book"),
        CacheInvalidatingHandler(failing, cache, "book"),
    ]

    with pytest.raises(RuntimeError, match="database down"):
        await release_all_expired(
            lambda: handlers.pop(0),
            ReleaseExpiredReservationsCommand(ttl_seconds=300, batch_size=2),
        )

    cache.invalidate_all.assert_awaited_once_with("book")

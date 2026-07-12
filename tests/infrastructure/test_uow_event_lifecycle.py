"""Outbox staging must never acknowledge events before database commit."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.catalog import Author, Book, BookId, Title
from src.infrastructure.adapters.catalog.catalog_unit_of_work import CatalogUnitOfWork


def _dirty_book() -> Book:
    book = Book(id=BookId("book-events"), title=Title("Events"), author=Author("Tester"))
    book.reserve(
        patron_id="patron-events",
        borrower_email="events@example.com",
        reserved_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
        reservation_id="11111111-1111-4111-8111-111111111111",
    )
    return book


def _uow(book: Book, commit_side_effect=None) -> CatalogUnitOfWork:
    uow = CatalogUnitOfWork(MagicMock())
    uow._session = MagicMock()
    uow._session.commit = AsyncMock(side_effect=commit_side_effect)
    uow._session.rollback = AsyncMock()
    uow._session.add = MagicMock()
    uow.identity_map = {book.id.value: book}
    uow.dirty_ids = {book.id.value}
    uow.command_receipts = MagicMock()
    uow.command_receipts.pending = []
    return uow


@pytest.mark.asyncio
async def test_successful_commit_clears_only_dirty_aggregate_events():
    book = _dirty_book()
    uow = _uow(book)

    await uow.commit()

    assert book.get_domain_events() == []
    assert uow.dirty_ids == set()


@pytest.mark.asyncio
async def test_failed_commit_preserves_events_for_retry_or_diagnostics():
    book = _dirty_book()
    uow = _uow(book, RuntimeError("commit failed"))

    with pytest.raises(RuntimeError, match="commit failed"):
        await uow.commit()

    assert len(book.get_domain_events()) == 1
    assert uow.dirty_ids == {book.id.value}

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.query_handlers.pagination import InvalidPaginationError
from src.infrastructure.adapters.catalog.book_query_repository import BookQueryRepository
from src.infrastructure.adapters.lending.loan_query_repository import (
    LoanQueryRepository,
    _cursor_datetime,
)
from src.infrastructure.exceptions import SearchEngineException


class PassThroughBreaker:
    async def execute(self, operation, *args, **kwargs):
        return await operation(*args, **kwargs)


@pytest.mark.asyncio
async def test_overdue_query_is_computed_from_due_date_at_request_time():
    es = MagicMock()
    es.search = AsyncMock(return_value={"total": 1, "hits": [{
        "id": "loan-1",
        "patron_id": "patron-1",
        "patron_email": "patron@example.test",
        "catalog_book_id": "book-1",
        "book_title": "Title",
        "borrowed_at": "2026-06-01T00:00:00Z",
        "due_date": "2026-06-15T00:00:00Z",
        "returned_at": None,
        "status": "active",
        "_sort": ["2026-06-15T00:00:00Z", "loan-1"],
    }]})
    repository = LoanQueryRepository(
        session_factory=MagicMock(),
        elasticsearch_client=es,
        circuit_breaker=PassThroughBreaker(),
        logger=MagicMock(),
    )

    loans = await repository.find_overdue(limit=10)

    query = es.search.await_args.kwargs["query"]
    filters = query["bool"]["filter"]
    assert query["bool"]["must_not"] == [
        {"terms": {"status": ["returned", "cancelled"]}}
    ]
    range_filter = next(item for item in filters if "range" in item)
    assert "lt" in range_filter["range"]["due_date"]
    assert isinstance(loans[0].due_date, datetime)


@pytest.mark.asyncio
async def test_book_page_has_consistent_sort_cursor_and_reserved_semantics():
    es = MagicMock()
    es.search = AsyncMock(return_value={"total": 1, "hits": [{
        "id": "book-1",
        "title": "Alpha",
        "author": "Author",
        "status": "reserved",
        "is_borrowed": True,
        "borrowed_at": None,
        "return_due_date": None,
        "_sort": ["Alpha", "book-1"],
    }]})
    repository = BookQueryRepository(
        session_factory=MagicMock(),
        elasticsearch_client=es,
        circuit_breaker=PassThroughBreaker(),
        logger=MagicMock(),
    )

    page = await repository.find_page(limit=1)

    assert es.search.await_args.kwargs["sort"] == repository.ES_SORT
    assert page.items[0].is_borrowed is False
    assert page.next_cursor is not None

    es.search.side_effect = SearchEngineException("ES down")
    with pytest.raises(SearchEngineException):
        await repository.find_page(limit=1, cursor=page.next_cursor)


@pytest.mark.asyncio
async def test_invalid_deep_offset_never_reaches_es_or_breaker():
    es = MagicMock()
    es.search = AsyncMock()
    breaker = MagicMock()
    breaker.execute = AsyncMock()
    repository = BookQueryRepository(
        session_factory=MagicMock(),
        elasticsearch_client=es,
        circuit_breaker=breaker,
        logger=MagicMock(),
    )

    with pytest.raises(InvalidPaginationError):
        await repository.find_page(limit=1_000, offset=9_001)

    breaker.execute.assert_not_awaited()
    es.search.assert_not_awaited()


def test_only_active_means_all_non_terminal_loan_states():
    repository = LoanQueryRepository(
        session_factory=MagicMock(),
        elasticsearch_client=MagicMock(),
        circuit_breaker=PassThroughBreaker(),
        logger=MagicMock(),
    )

    query = repository._build_es_query(patron_id="patron-1", only_active=True)

    assert query["bool"]["filter"] == [{"term": {"patron_id": "patron-1"}}]
    assert query["bool"]["must_not"] == [
        {"terms": {"status": ["returned", "cancelled"]}}
    ]


def test_elasticsearch_epoch_millis_cursor_is_portable_to_postgresql():
    expected = datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc)
    epoch_millis = int(expected.timestamp() * 1_000)
    value = _cursor_datetime(epoch_millis)

    assert value == expected

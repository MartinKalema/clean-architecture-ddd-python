"""PostgreSQL fallback preserves the same literal search and cursor contract."""
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.adapters.catalog.book_model import BookModel
from src.infrastructure.adapters.catalog.book_query_repository import BookQueryRepository
from src.infrastructure.adapters.resilience import CircuitBreaker
from src.infrastructure.exceptions import SearchEngineException


def _repository(test_db) -> BookQueryRepository:
    es = MagicMock()
    es.search = AsyncMock(side_effect=SearchEngineException("ES down"))
    es.count = AsyncMock(side_effect=SearchEngineException("ES down"))
    return BookQueryRepository(
        session_factory=async_sessionmaker(
            bind=test_db.engine,
            expire_on_commit=False,
        ),
        elasticsearch_client=es,
        circuit_breaker=CircuitBreaker(
            name="read-pagination-es",
            failure_threshold=20,
            timeout=60,
        ),
        logger=MagicMock(),
    )


@pytest_asyncio.fixture
async def books(test_db):
    rows = [
        BookModel(id="book-b", title="alpha", author="A", status="available"),
        BookModel(id="book-a", title="Alpha", author="A", status="available"),
        BookModel(id="book-c", title="Beta", author="A", status="available"),
        BookModel(id="book-d", title="100% Reliable", author="A", status="available"),
        BookModel(id="book-e", title="100X Reliable", author="A", status="available"),
    ]
    async with test_db.session_factory() as session:
        session.add_all(rows)
        await session.commit()
    return rows


@pytest.mark.asyncio
async def test_cursor_pages_are_deterministic_across_equal_casefolded_titles(
    test_db, books
):
    repository = _repository(test_db)

    first = await repository.find_page(limit=2)
    second = await repository.find_page(limit=2, cursor=first.next_cursor)

    assert [book.id for book in first.items] == ["book-d", "book-e"]
    assert [book.id for book in second.items] == ["book-a", "book-b"]
    assert not ({book.id for book in first.items} & {book.id for book in second.items})


@pytest.mark.asyncio
async def test_substring_fallback_escapes_user_wildcard_characters(test_db, books):
    repository = _repository(test_db)

    page = await repository.find_page(title_contains="100%", limit=10)

    assert [book.id for book in page.items] == ["book-d"]

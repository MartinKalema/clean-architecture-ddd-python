"""
Integration tests for the PostgreSQL fallback of the query repositories.

When Elasticsearch is unavailable (or its circuit breaker is open),
searches must degrade to PostgreSQL instead of failing or returning
empty results.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.adapters.catalog import BookQueryRepository
from src.infrastructure.adapters.catalog.book_model import BookModel
from src.infrastructure.adapters.resilience import CircuitBreaker
from src.infrastructure.exceptions import SearchEngineException


def _broken_es_client():
    es_client = MagicMock()
    es_client.search = AsyncMock(side_effect=SearchEngineException("ES down"))
    es_client.count = AsyncMock(side_effect=SearchEngineException("ES down"))
    return es_client


def _repository(test_db, es_client) -> BookQueryRepository:
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    return BookQueryRepository(
        session_factory=session_factory,
        elasticsearch_client=es_client,
        circuit_breaker=CircuitBreaker(name="es-test", failure_threshold=2, timeout=60.0),
        logger=MagicMock(),
    )


async def _seed_books(test_db):
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    borrowed_at = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    async with session_factory() as session:
        session.add(BookModel(
            id="fallback-1", title="Fallback Patterns", author="Ada Resilience",
            status="available", version=0,
        ))
        session.add(BookModel(
            id="fallback-2", title="Fallback in Practice", author="Grace Degraded",
            status="borrowed",
            reservation_id="40000000-0000-4000-8000-000000000002",
            reservation_generation=1,
            reserved_patron_id="fallback-patron",
            reserved_patron_email="fallback@example.com",
            current_loan_id="fallback-loan",
            borrowed_at=borrowed_at,
            return_due_date=borrowed_at + timedelta(days=14),
            version=0,
        ))
        await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def seeded_books(test_db, clean_integration_tables):
    await _seed_books(test_db)


@pytest.mark.asyncio
async def test_find_all_falls_back_to_postgresql(test_db):
    repository = _repository(test_db, _broken_es_client())

    books = await repository.find_all(title_contains="Fallback")

    titles = {book.title for book in books}
    assert titles == {"Fallback Patterns", "Fallback in Practice"}


@pytest.mark.asyncio
async def test_fallback_respects_filters(test_db):
    repository = _repository(test_db, _broken_es_client())

    available = await repository.find_all(title_contains="Fallback", only_available=True)

    assert [book.id for book in available] == ["fallback-1"]
    assert available[0].is_borrowed is False


@pytest.mark.asyncio
async def test_count_falls_back_to_postgresql(test_db):
    repository = _repository(test_db, _broken_es_client())

    count = await repository.count(only_borrowed=True)

    assert count >= 1  # at least the seeded borrowed book


@pytest.mark.asyncio
async def test_open_circuit_still_serves_from_postgresql(test_db):
    es_client = _broken_es_client()
    repository = _repository(test_db, es_client)

    # Trip the breaker (failure_threshold=2)
    await repository.find_all(title_contains="Fallback")
    await repository.find_all(title_contains="Fallback")
    es_calls_before = es_client.search.await_count

    # Circuit now open: ES is not even attempted, results still served
    books = await repository.find_all(title_contains="Fallback")

    assert es_client.search.await_count == es_calls_before
    assert len(books) == 2

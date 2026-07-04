"""
Integration tests for the borrow-a-book choreography.

The full cross-context flow, driven exactly as the event worker drives it:
borrow commits in the Catalog context and stages CatalogBookBorrowed in
the outbox; the deserialized event is handled by the Lending context's
reaction, which creates the loan — or compensates by returning the book.
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.command_handlers import (
    AddBookCommand,
    AddBookHandler,
    BorrowBookCommand,
    BorrowBookHandler,
)
from src.application.command_handlers.create_loan import CreateLoanHandler
from src.application.command_handlers.return_book import ReturnBookHandler
from src.application.event_handlers import CreateLoanOnBookBorrowedHandler
from src.domain.catalog import CatalogBookBorrowed
from src.infrastructure.adapters.catalog import CatalogUnitOfWork
from src.infrastructure.adapters.events import deserialize_event
from src.infrastructure.adapters.lending import LoanUnitOfWork
from src.infrastructure.adapters.outbox import OutboxMessageModel


async def _borrow_and_capture_event(test_db, title: str, email: str):
    """Add and borrow a book, then rebuild the event from its outbox row."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    catalog_uow = CatalogUnitOfWork(session_factory)
    logger = MagicMock()

    book = await AddBookHandler(catalog_uow, logger=logger).handle(
        AddBookCommand(title=title, author="Choreography Tester")
    )
    await BorrowBookHandler(catalog_uow, logger=logger).handle(
        BorrowBookCommand(book_id=book.id, borrower_email=email)
    )

    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel)
            .where(OutboxMessageModel.type == "CatalogBookBorrowed")
            .where(OutboxMessageModel.aggregateid == book.id)
        )
        row = result.scalar_one()

    event = deserialize_event(json.loads(row.payload))
    assert isinstance(event, CatalogBookBorrowed)
    return book, event, session_factory, catalog_uow


def _reaction_handler(session_factory, catalog_uow, patron):
    patron_repository = AsyncMock()
    patron_repository.find_by_email.return_value = patron
    logger = MagicMock()
    return CreateLoanOnBookBorrowedHandler(
        create_loan_handler=CreateLoanHandler(LoanUnitOfWork(session_factory), logger=logger),
        return_book_handler=ReturnBookHandler(catalog_uow, logger=logger),
        patron_query_repository=patron_repository,
        logger=logger,
    )


@pytest.mark.asyncio
async def test_borrow_creates_loan_through_the_event(test_db):
    book, event, session_factory, catalog_uow = await _borrow_and_capture_event(
        test_db, "Choreographed Borrow", "choreo@example.com"
    )
    handler = _reaction_handler(
        session_factory, catalog_uow, patron={"id": "patron-choreo-1", "is_suspended": False}
    )

    await handler.handle(event)

    # Loan exists in the Lending context, sourced entirely from the event
    loan_uow = LoanUnitOfWork(session_factory)
    async with loan_uow:
        loan = await loan_uow.loans.get_active_loan_for_book(book.id)
    assert loan is not None
    assert loan.patron_id == "patron-choreo-1"
    assert loan.patron_email == "choreo@example.com"
    assert loan.due_date.value == event.return_due_date  # catalog's due date honored

    # And the loan's own LoanCreated event is staged for the next hop (email)
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel)
            .where(OutboxMessageModel.type == "LoanCreated")
            .where(OutboxMessageModel.aggregateid == loan.id.value)
        )
        assert result.scalar_one() is not None


@pytest.mark.asyncio
async def test_unknown_patron_releases_the_book(test_db):
    book, event, session_factory, catalog_uow = await _borrow_and_capture_event(
        test_db, "Compensated Borrow", "nobody@example.com"
    )
    handler = _reaction_handler(session_factory, catalog_uow, patron=None)

    await handler.handle(event)

    # No loan was created...
    loan_uow = LoanUnitOfWork(session_factory)
    async with loan_uow:
        assert await loan_uow.loans.get_active_loan_for_book(book.id) is None

    # ...and the compensation returned the book to availability
    async with catalog_uow:
        compensated = await catalog_uow.books.get_by_id(book.id)
        assert compensated.is_borrowed is False

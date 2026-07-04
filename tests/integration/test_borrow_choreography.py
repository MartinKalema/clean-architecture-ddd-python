"""
Integration tests for the borrow-a-book saga (reserve -> loan -> confirm).

The full cross-context flow, driven exactly as the event worker drives it:
the borrow commits a RESERVED semantic lock and stages CatalogBookReserved
in the outbox; lending reacts by creating the loan; the loan's LoanCreated
confirms the reservation into a final borrow — or, on rejection, the
reservation is released. Reservations that outlive the TTL are reaped.
"""
import json
from datetime import datetime, timedelta
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
from src.application.command_handlers.confirm_book_borrow import (
    ConfirmBookBorrowHandler,
)
from src.application.command_handlers.create_loan import CreateLoanHandler
from src.application.command_handlers.release_book_reservation import (
    ReleaseBookReservationHandler,
)
from src.application.command_handlers.release_expired_reservations import (
    ReleaseExpiredReservationsCommand,
    ReleaseExpiredReservationsHandler,
)
from src.application.event_handlers import (
    ConfirmBorrowOnLoanCreatedHandler,
    CreateLoanOnBookReservedHandler,
)
from src.domain.catalog import BookStatus, CatalogBookReserved
from src.domain.lending import LoanCreated
from src.infrastructure.adapters.catalog import CatalogUnitOfWork
from src.infrastructure.adapters.events import deserialize_event
from src.infrastructure.adapters.lending import LoanUnitOfWork
from src.infrastructure.adapters.outbox import OutboxMessageModel


async def _outbox_event(session_factory, event_type, aggregate_id):
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel)
            .where(OutboxMessageModel.type == event_type)
            .where(OutboxMessageModel.aggregateid == aggregate_id)
        )
        row = result.scalar_one()
    return deserialize_event(json.loads(row.payload))


async def _reserve_and_capture_event(test_db, title: str, email: str):
    """Add and borrow a book, then rebuild the event from its outbox row."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    catalog_uow = CatalogUnitOfWork(session_factory)
    logger = MagicMock()

    book = await AddBookHandler(catalog_uow, logger=logger).handle(
        AddBookCommand(title=title, author="Choreography Tester")
    )
    reserved = await BorrowBookHandler(catalog_uow, logger=logger).handle(
        BorrowBookCommand(book_id=book.id, borrower_email=email)
    )
    assert reserved.status == "reserved"

    event = await _outbox_event(session_factory, "CatalogBookReserved", book.id)
    assert isinstance(event, CatalogBookReserved)
    return book, event, session_factory, catalog_uow


def _lending_reaction(session_factory, catalog_uow, patron):
    patron_repository = AsyncMock()
    patron_repository.find_by_email.return_value = patron
    logger = MagicMock()
    return CreateLoanOnBookReservedHandler(
        create_loan_handler=CreateLoanHandler(LoanUnitOfWork(session_factory), logger=logger),
        release_book_reservation_handler=ReleaseBookReservationHandler(catalog_uow, logger=logger),
        patron_query_repository=patron_repository,
        logger=logger,
    )


async def _book_status(catalog_uow, book_id) -> BookStatus:
    async with catalog_uow:
        book = await catalog_uow.books.get_by_id(book_id)
        return book.status


@pytest.mark.asyncio
async def test_full_saga_reserve_loan_confirm(test_db):
    book, event, session_factory, catalog_uow = await _reserve_and_capture_event(
        test_db, "Choreographed Borrow", "choreo@example.com"
    )

    # Step 2: lending reacts to the reservation
    await _lending_reaction(
        session_factory, catalog_uow, patron={"id": "patron-choreo-1", "is_suspended": False}
    ).handle(event)

    loan_uow = LoanUnitOfWork(session_factory)
    async with loan_uow:
        loan = await loan_uow.loans.get_active_loan_for_book(book.id)
    assert loan is not None
    assert loan.patron_id == "patron-choreo-1"
    assert loan.due_date.value == event.return_due_date  # catalog's due date honored

    # Between loan creation and confirmation the lock is still held
    assert await _book_status(catalog_uow, book.id) == BookStatus.RESERVED

    # Step 3: catalog reacts to LoanCreated and confirms the borrow
    loan_created = await _outbox_event(session_factory, "LoanCreated", loan.id.value)
    assert isinstance(loan_created, LoanCreated)
    confirm_reaction = ConfirmBorrowOnLoanCreatedHandler(
        ConfirmBookBorrowHandler(catalog_uow, logger=MagicMock()), logger=MagicMock()
    )
    await confirm_reaction.handle(loan_created)

    assert await _book_status(catalog_uow, book.id) == BookStatus.BORROWED
    # The final fact is published for downstream consumers
    confirmed = await _outbox_event(session_factory, "CatalogBookBorrowed", book.id)
    assert confirmed.borrower_email == "choreo@example.com"


@pytest.mark.asyncio
async def test_unknown_patron_releases_the_reservation(test_db):
    book, event, session_factory, catalog_uow = await _reserve_and_capture_event(
        test_db, "Compensated Borrow", "nobody@example.com"
    )

    await _lending_reaction(session_factory, catalog_uow, patron=None).handle(event)

    loan_uow = LoanUnitOfWork(session_factory)
    async with loan_uow:
        assert await loan_uow.loans.get_active_loan_for_book(book.id) is None

    assert await _book_status(catalog_uow, book.id) == BookStatus.AVAILABLE
    released = await _outbox_event(session_factory, "CatalogBookReleased", book.id)
    assert "no patron registered" in released.reason


@pytest.mark.asyncio
async def test_reaper_releases_expired_reservations(test_db):
    book, _, session_factory, catalog_uow = await _reserve_and_capture_event(
        test_db, "Stale Reservation", "slow@example.com"
    )

    # Backdate the reservation past the TTL
    async with session_factory() as session:
        from src.infrastructure.adapters.catalog.book_model import BookModel
        db_book = (await session.execute(
            select(BookModel).where(BookModel.id == book.id)
        )).scalar_one()
        db_book.reserved_at = datetime.now() - timedelta(hours=1)
        await session.commit()

    reaper = ReleaseExpiredReservationsHandler(
        CatalogUnitOfWork(session_factory), logger=MagicMock()
    )
    result = await reaper.handle(ReleaseExpiredReservationsCommand(ttl_seconds=300))

    assert result.released_count == 1
    assert await _book_status(catalog_uow, book.id) == BookStatus.AVAILABLE


@pytest.mark.asyncio
async def test_reaper_leaves_fresh_reservations_alone(test_db):
    book, _, session_factory, catalog_uow = await _reserve_and_capture_event(
        test_db, "Fresh Reservation", "fast@example.com"
    )

    reaper = ReleaseExpiredReservationsHandler(
        CatalogUnitOfWork(session_factory), logger=MagicMock()
    )
    result = await reaper.handle(ReleaseExpiredReservationsCommand(ttl_seconds=300))

    assert result.released_count == 0
    assert await _book_status(catalog_uow, book.id) == BookStatus.RESERVED

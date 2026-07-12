"""Integration tests for the correlated borrow and return workflows."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
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
from src.application.command_handlers.cancel_loan import CancelLoanHandler
from src.application.command_handlers.confirm_book_borrow import (
    ConfirmBookBorrowHandler,
)
from src.application.command_handlers.create_loan import (
    CreateLoanCommand,
    CreateLoanHandler,
    CreateLoanResult,
)
from src.application.command_handlers.release_book_reservation import (
    ReleaseBookReservationHandler,
)
from src.application.command_handlers.release_expired_reservations import (
    ReleaseExpiredReservationsCommand,
    ReleaseExpiredReservationsHandler,
)
from src.application.command_handlers.return_book import ReturnBookHandler
from src.application.command_handlers.return_loan import (
    ReturnLoanCommand,
    ReturnLoanHandler,
)
from src.application.event_handlers import (
    CancelLoanOnBookReleasedHandler,
    ConfirmBorrowOnLoanCreatedHandler,
    CreateLoanOnBookReservedHandler,
    ReturnBookOnLoanCompletedHandler,
)
from src.application.ports import BorrowerProfile
from src.application.query_handlers import PatronReadModel
from src.domain.catalog import (
    BookStatus,
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
)
from src.domain.lending import (
    LoanCompleted,
    LoanCreated,
    LoanStatus,
    PatronBorrowingLimitReachedException,
)
from src.infrastructure.adapters.catalog import CatalogUnitOfWork
from src.infrastructure.adapters.events import (
    deserialize_event,
    outbox_type_for_event_class,
)
from src.infrastructure.adapters.lending import LoanUnitOfWork
from src.infrastructure.adapters.lending.loan_model import LoanModel
from src.infrastructure.adapters.outbox import OutboxMessageModel
from src.infrastructure.adapters.patron import PatronUnitOfWork


def _patron(patron_id: str, email: str) -> PatronReadModel:
    return PatronReadModel(
        id=patron_id,
        name="Choreo Patron",
        first_name="Choreo",
        last_name="Patron",
        email=email,
        membership_tier="regular",
        is_suspended=False,
        suspended_reason=None,
        registered_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


class _Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def _directory(patron: PatronReadModel):
    profile = BorrowerProfile(
        patron_id=patron.id,
        email=patron.email,
        is_eligible=not patron.is_suspended,
        membership_tier=patron.membership_tier,
        ineligible_reason="patron is suspended" if patron.is_suspended else None,
    )
    directory = AsyncMock()
    directory.find_by_email.return_value = profile
    directory.get_by_id.return_value = profile
    return directory


async def _latest_outbox_event(session_factory, event_class, aggregate_id):
    wire_type = outbox_type_for_event_class(event_class)
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel)
            .where(OutboxMessageModel.type == wire_type)
            .where(OutboxMessageModel.aggregateid == aggregate_id)
            .order_by(
                OutboxMessageModel.occurred_at.desc(),
                OutboxMessageModel.id.desc(),
            )
        )
        row = result.scalars().first()
    assert row is not None, f"missing {event_class.__name__} for {aggregate_id}"
    return deserialize_event(json.loads(row.payload))


async def _reserve(test_db, title: str, patron: PatronReadModel):
    session_factory = async_sessionmaker(
        bind=test_db.engine, expire_on_commit=False
    )
    catalog_uow = CatalogUnitOfWork(session_factory)
    logger = MagicMock()
    book = await AddBookHandler(catalog_uow, logger=logger).handle(
        AddBookCommand(title=title, author="Choreography Tester")
    )
    reserved = await BorrowBookHandler(
        catalog_uow,
        borrower_directory=_directory(patron),
        logger=logger,
        clock=_Clock(),
    ).handle(
        BorrowBookCommand(book_id=book.id, borrower_email=patron.email)
    )
    assert reserved.status == BookStatus.RESERVED.value

    event = await _latest_outbox_event(
        session_factory, CatalogBookReserved, book.id
    )
    assert isinstance(event, CatalogBookReserved)
    return book, event, session_factory


def _loan_reaction(session_factory, patron: PatronReadModel):
    logger = MagicMock()
    directory = _directory(patron)
    return CreateLoanOnBookReservedHandler(
        create_loan_operation=CreateLoanHandler(
            LoanUnitOfWork(session_factory),
            borrower_directory=directory,
            logger=logger,
        ),
        release_book_reservation_operation=ReleaseBookReservationHandler(
            CatalogUnitOfWork(session_factory), logger=logger, clock=_Clock()
        ),
        logger=logger,
    )


def _confirm_reaction(session_factory):
    logger = MagicMock()
    return ConfirmBorrowOnLoanCreatedHandler(
        confirm_book_borrow_operation=ConfirmBookBorrowHandler(
            CatalogUnitOfWork(session_factory), logger=logger, clock=_Clock()
        ),
        cancel_loan_operation=CancelLoanHandler(
            LoanUnitOfWork(session_factory), logger=logger
        ),
        logger=logger,
    )


async def _book(session_factory, book_id):
    async with CatalogUnitOfWork(session_factory) as uow:
        return await uow.books.get_by_id(book_id)


async def _loan(session_factory, loan_id):
    async with LoanUnitOfWork(session_factory) as uow:
        return await uow.loans.get_by_id(loan_id)


async def _complete_borrow(test_db, title, patron):
    book, reserved, session_factory = await _reserve(test_db, title, patron)
    await _loan_reaction(session_factory, patron).handle(reserved)

    async with LoanUnitOfWork(session_factory) as uow:
        loan = await uow.loans.get_active_loan_for_book(book.id)
    assert loan is not None

    created = await _latest_outbox_event(
        session_factory, LoanCreated, loan.id.value
    )
    assert isinstance(created, LoanCreated)
    await _confirm_reaction(session_factory).handle(created)
    return book, reserved, loan, created, session_factory


@pytest.mark.asyncio
async def test_full_saga_persists_exact_correlation_and_confirms_catalog(test_db):
    patron = _patron("patron-choreo-1", "choreo@example.com")
    book_result, reserved, loan, _, session_factory = await _complete_borrow(
        test_db, "Choreographed Borrow", patron
    )

    assert loan.reservation_id.value == reserved.reservation_id
    assert loan.reservation_generation == reserved.reservation_generation
    assert loan.patron_id == patron.id
    assert loan.patron_email == patron.email
    assert loan.book_title == book_result.title
    assert loan.due_date.value == reserved.reserved_at + timedelta(days=14)

    catalog_book = await _book(session_factory, book_result.id)
    assert catalog_book.status == BookStatus.BORROWED
    assert catalog_book.current_loan_id == loan.id.value
    assert catalog_book.reservation_id.value == reserved.reservation_id

    definitive = await _latest_outbox_event(
        session_factory, CatalogBookBorrowed, book_result.id
    )
    assert definitive.loan_id == loan.id.value
    assert definitive.borrower_email == patron.email


@pytest.mark.asyncio
async def test_final_lending_decision_enforces_patron_tier_limit(test_db):
    patron = _patron("patron-at-limit", "at-limit@example.com")
    book_result, reserved, session_factory = await _reserve(
        test_db, "Borrowing Limit", patron
    )
    async with session_factory() as session:
        session.add_all(
            [
                LoanModel(
                    id=f"limit-loan-{index}",
                    reservation_id=(
                        f"00000000-0000-4000-8000-{index:012d}"
                    ),
                    reservation_generation=1,
                    patron_id=patron.id,
                    patron_email=patron.email,
                    catalog_book_id=f"limit-book-{index}",
                    book_title=f"Limit Book {index}",
                    borrowed_at=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
                    due_date=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
                    status="active",
                    version=0,
                )
                for index in range(5)
            ]
        )
        await session.commit()

    await _loan_reaction(session_factory, patron).handle(reserved)

    catalog_book = await _book(session_factory, book_result.id)
    assert catalog_book.status == BookStatus.AVAILABLE
    async with LoanUnitOfWork(session_factory) as uow:
        assert await uow.loans.get_active_loan_for_book(book_result.id) is None
    released = await _latest_outbox_event(
        session_factory, CatalogBookReleased, book_result.id
    )
    assert "borrowing limit" in released.reason


@pytest.mark.asyncio
async def test_concurrent_last_slot_admission_creates_exactly_one_loan(test_db):
    """The application UoW fence makes capacity admission linearizable."""
    if not test_db.db_url.startswith("postgresql"):
        pytest.skip("PostgreSQL advisory-lock contract")
    patron = _patron("patron-last-slot", "last-slot@example.com")
    session_factory = async_sessionmaker(
        bind=test_db.engine, expire_on_commit=False
    )
    borrowed_at = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    async with session_factory() as session:
        session.add_all(
            [
                LoanModel(
                    id=f"existing-slot-loan-{index}",
                    reservation_id=f"20000000-0000-4000-8000-{index:012d}",
                    reservation_generation=1,
                    patron_id=patron.id,
                    patron_email=patron.email,
                    catalog_book_id=f"existing-slot-book-{index}",
                    book_title=f"Existing Slot Book {index}",
                    borrowed_at=borrowed_at,
                    due_date=borrowed_at + timedelta(days=14),
                    status="active",
                    version=0,
                )
                for index in range(4)
            ]
        )
        await session.commit()

    directory = _directory(patron)
    handlers = [
        CreateLoanHandler(
            LoanUnitOfWork(session_factory),
            borrower_directory=directory,
            logger=MagicMock(),
        )
        for _ in range(2)
    ]
    commands = [
        CreateLoanCommand(
            reservation_id=f"30000000-0000-4000-8000-{index:012d}",
            reservation_generation=1,
            patron_id=patron.id,
            patron_email=patron.email,
            catalog_book_id=f"candidate-slot-book-{index}",
            book_title=f"Candidate Slot Book {index}",
            borrowed_at=borrowed_at,
        )
        for index in range(2)
    ]

    outcomes = await asyncio.gather(
        *(handler.handle(command) for handler, command in zip(handlers, commands)),
        return_exceptions=True,
    )

    assert sum(isinstance(value, CreateLoanResult) for value in outcomes) == 1
    assert sum(
        isinstance(value, PatronBorrowingLimitReachedException)
        for value in outcomes
    ) == 1
    async with session_factory() as session:
        rows = await session.execute(
            select(LoanModel).where(LoanModel.patron_id == patron.id)
        )
        assert len(rows.scalars().all()) == 5


@pytest.mark.asyncio
async def test_patron_and_lending_uows_share_the_same_admission_fence(test_db):
    """Suspension/tier mutation and loan creation cannot pass concurrently."""
    if not test_db.db_url.startswith("postgresql"):
        pytest.skip("PostgreSQL advisory-lock contract")
    session_factory = async_sessionmaker(
        bind=test_db.engine, expire_on_commit=False
    )
    attempting = asyncio.Event()

    async def acquire_from_lending() -> None:
        async with LoanUnitOfWork(session_factory) as lending:
            attempting.set()
            await lending.acquire_borrowing_fence("patron-shared-fence")
            await lending.rollback()

    async with PatronUnitOfWork(session_factory) as patron:
        await patron.acquire_borrowing_fence("patron-shared-fence")
        contender = asyncio.create_task(acquire_from_lending())
        await attempting.wait()
        await asyncio.sleep(0.05)
        assert not contender.done()
        await patron.rollback()
        await asyncio.wait_for(contender, timeout=2)


@pytest.mark.asyncio
async def test_authoritative_loan_return_reconciles_exact_catalog_loan(test_db):
    patron = _patron("patron-return-1", "return@example.com")
    book_result, _, loan, _, session_factory = await _complete_borrow(
        test_db, "Authoritative Return", patron
    )

    await ReturnLoanHandler(
        LoanUnitOfWork(session_factory), logger=MagicMock(), clock=_Clock()
    ).handle(ReturnLoanCommand(loan_id=loan.id.value))
    completed = await _latest_outbox_event(
        session_factory, LoanCompleted, loan.id.value
    )
    assert isinstance(completed, LoanCompleted)

    await ReturnBookOnLoanCompletedHandler(
        ReturnBookHandler(
            CatalogUnitOfWork(session_factory), logger=MagicMock(), clock=_Clock()
        ),
        logger=MagicMock(),
    ).handle(completed)

    returned_loan = await _loan(session_factory, loan.id.value)
    catalog_book = await _book(session_factory, book_result.id)
    assert returned_loan.status == LoanStatus.RETURNED
    assert catalog_book.status == BookStatus.AVAILABLE
    assert catalog_book.current_loan_id is None
    assert catalog_book.last_completed_loan_id == loan.id.value


@pytest.mark.asyncio
async def test_expired_reservation_cancels_its_loan_and_cannot_hijack_new_owner(
    test_db,
):
    first_patron = _patron("patron-stale-1", "stale@example.com")
    book_result, old_reservation, session_factory = await _reserve(
        test_db, "Fenced Reservation", first_patron
    )
    await _loan_reaction(session_factory, first_patron).handle(old_reservation)

    async with LoanUnitOfWork(session_factory) as uow:
        old_loan = await uow.loans.get_active_loan_for_book(book_result.id)
    assert old_loan is not None
    delayed_created = await _latest_outbox_event(
        session_factory, LoanCreated, old_loan.id.value
    )

    # Expire the semantic lock after Lending committed but before Catalog
    # observed LoanCreated.
    from src.infrastructure.adapters.catalog.book_model import BookModel

    async with session_factory() as session:
        row = (
            await session.execute(
                select(BookModel).where(BookModel.id == book_result.id)
            )
        ).scalar_one()
        row.reserved_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()

    result = await ReleaseExpiredReservationsHandler(
        CatalogUnitOfWork(session_factory), logger=MagicMock(), clock=_Clock()
    ).handle(ReleaseExpiredReservationsCommand(ttl_seconds=300))
    assert result.released_count == 1

    released = await _latest_outbox_event(
        session_factory, CatalogBookReleased, book_result.id
    )
    assert isinstance(released, CatalogBookReleased)
    await CancelLoanOnBookReleasedHandler(
        CancelLoanHandler(LoanUnitOfWork(session_factory), logger=MagicMock()),
        logger=MagicMock(),
    ).handle(released)
    assert (await _loan(session_factory, old_loan.id.value)).status == LoanStatus.CANCELLED

    # A different owner starts the next generation.
    second_patron = _patron("patron-stale-2", "new-owner@example.com")
    await BorrowBookHandler(
        CatalogUnitOfWork(session_factory),
        borrower_directory=_directory(second_patron),
        logger=MagicMock(),
        clock=_Clock(),
    ).handle(
        BorrowBookCommand(
            book_id=book_result.id, borrower_email=second_patron.email
        )
    )
    new_reservation = await _latest_outbox_event(
        session_factory, CatalogBookReserved, book_result.id
    )
    assert new_reservation.reservation_id != old_reservation.reservation_id
    assert (
        new_reservation.reservation_generation
        == old_reservation.reservation_generation + 1
    )

    # The delayed confirmation can only cancel its own tentative loan. It
    # cannot confirm or release the newer owner's reservation.
    await _confirm_reaction(session_factory).handle(delayed_created)
    catalog_book = await _book(session_factory, book_result.id)
    assert catalog_book.status == BookStatus.RESERVED
    assert catalog_book.reservation_id.value == new_reservation.reservation_id
    assert catalog_book.reserved_patron_id == second_patron.id


@pytest.mark.asyncio
async def test_old_completion_cannot_return_a_newer_reservation(test_db):
    first_patron = _patron("patron-old-return-1", "old-return@example.com")
    book_result, _, loan, _, session_factory = await _complete_borrow(
        test_db, "Stale Return Fence", first_patron
    )
    await ReturnLoanHandler(
        LoanUnitOfWork(session_factory), logger=MagicMock(), clock=_Clock()
    ).handle(ReturnLoanCommand(loan_id=loan.id.value))
    old_completion = await _latest_outbox_event(
        session_factory, LoanCompleted, loan.id.value
    )
    return_reaction = ReturnBookOnLoanCompletedHandler(
        ReturnBookHandler(
            CatalogUnitOfWork(session_factory), logger=MagicMock(), clock=_Clock()
        ),
        logger=MagicMock(),
    )
    await return_reaction.handle(old_completion)

    second_patron = _patron("patron-old-return-2", "next-return@example.com")
    await BorrowBookHandler(
        CatalogUnitOfWork(session_factory),
        _directory(second_patron),
        logger=MagicMock(),
        clock=_Clock(),
    ).handle(
        BorrowBookCommand(
            book_id=book_result.id, borrower_email=second_patron.email
        )
    )
    before_replay = await _book(session_factory, book_result.id)

    await return_reaction.handle(old_completion)

    after_replay = await _book(session_factory, book_result.id)
    assert after_replay.status == BookStatus.RESERVED
    assert after_replay.reservation_id == before_replay.reservation_id
    assert after_replay.reserved_patron_id == second_patron.id

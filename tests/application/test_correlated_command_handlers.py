"""Application command tests for correlation and idempotency boundaries."""
from datetime import datetime as _datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.command_handlers.borrow_book import (
    BorrowBookCommand,
    BorrowBookHandler,
)
from src.application.command_handlers.cancel_loan import (
    CancelLoanCommand,
    CancelLoanHandler,
)
from src.application.command_handlers.create_loan import (
    CreateLoanCommand,
    CreateLoanHandler,
)
from src.application.ports import BorrowerProfile
from src.domain.lending import (
    ConcurrentLoanCreationException,
    PatronBorrowingLimitReachedException,
    ReservationCorrelationMismatchException,
)


RESERVATION_ID = "11111111-1111-4111-8111-111111111111"
CANONICAL_RESERVATION_ID = "abcdefab-cdef-4abc-8def-abcdefabcdef"


class datetime(_datetime):
    """UTC-aware datetime constructor for application workflow fixtures."""

    def __new__(cls, *args, **kwargs):
        if len(args) < 8:
            kwargs.setdefault("tzinfo", timezone.utc)
        return super().__new__(cls, *args, **kwargs)


def _uow(repository_name: str):
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    repository = AsyncMock()
    if repository_name == "loans":
        repository.count_outstanding_for_patron.return_value = 0
    setattr(uow, repository_name, repository)
    uow.command_receipts = AsyncMock()
    uow.command_receipts.get.return_value = None
    uow.borrow_operations = AsyncMock()
    uow.acquire_borrowing_fence = AsyncMock()
    uow.commit = AsyncMock()
    return uow


def _borrower(membership_tier: str = "regular") -> BorrowerProfile:
    return BorrowerProfile(
        patron_id="patron-1",
        email="patron@example.com",
        is_eligible=True,
        membership_tier=membership_tier,
    )


def _create_loan_handler(uow, borrower: BorrowerProfile | None = None):
    directory = AsyncMock()
    directory.get_by_id.return_value = borrower or _borrower()
    return CreateLoanHandler(
        uow,
        borrower_directory=directory,
        logger=MagicMock(),
    )


class _Clock:
    def now(self):
        return datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_borrow_resolves_and_persists_patron_identity():
    uow = _uow("books")
    book = MagicMock()
    book.id.value = "book-1"
    book.title.value = "Domain-Driven Design"
    book.author.value = "Eric Evans"
    book.status.value = "reserved"
    book.is_borrowed = False
    book.return_due_date = None
    book.reservation_generation = 1
    book.reserve.return_value.value = RESERVATION_ID
    uow.books.get_by_id.return_value = book
    patrons = AsyncMock()
    patrons.find_by_email.return_value = _borrower()
    handler = BorrowBookHandler(uow, patrons, logger=MagicMock(), clock=_Clock())

    await handler.handle(
        BorrowBookCommand(
            book_id="book-1", borrower_email="PATRON@example.com"
        )
    )

    kwargs = book.reserve.call_args.kwargs
    assert kwargs["patron_id"] == "patron-1"
    assert kwargs["borrower_email"] == "patron@example.com"
    assert "loan_period_days" not in kwargs
    assert isinstance(kwargs["reserved_at"], datetime)
    uow.books.update.assert_awaited_once_with(book)
    uow.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_catalog_reservation_does_not_apply_tier_loan_period():
    uow = _uow("books")
    book = MagicMock()
    book.id.value = "book-1"
    book.title.value = "Domain-Driven Design"
    book.author.value = "Eric Evans"
    book.status.value = "reserved"
    book.is_borrowed = False
    book.return_due_date = None
    book.reservation_generation = 1
    book.reserve.return_value.value = RESERVATION_ID
    uow.books.get_by_id.return_value = book
    patrons = AsyncMock()
    patrons.find_by_email.return_value = _borrower("premium")

    result = await BorrowBookHandler(
        uow, patrons, logger=MagicMock(), clock=_Clock()
    ).handle(
        BorrowBookCommand(
            book_id="book-1", borrower_email="patron@example.com"
        )
    )

    assert "loan_period_days" not in book.reserve.call_args.kwargs
    assert result.return_due_date is None


@pytest.mark.asyncio
async def test_create_loan_deduplicates_by_reservation_before_book_activity():
    uow = _uow("loans")
    existing = MagicMock()
    existing.id.value = "loan-1"
    existing.reservation_id.value = CANONICAL_RESERVATION_ID
    existing.reservation_generation = 3
    existing.patron_id = "patron-1"
    existing.patron_email = "patron@example.com"
    existing.catalog_book_id = "book-1"
    existing.book_title = "Domain-Driven Design"
    existing.borrowed_at = datetime(2026, 7, 4)
    existing.due_date.value = datetime(2026, 7, 18)
    uow.loans.get_by_reservation_id.return_value = existing
    handler = _create_loan_handler(uow)

    result = await handler.handle(
        CreateLoanCommand(
            reservation_id=CANONICAL_RESERVATION_ID.upper(),
            reservation_generation=3,
            patron_id="patron-1",
            patron_email="patron@example.com",
            catalog_book_id="book-1",
            book_title="Domain-Driven Design",
            borrowed_at=datetime(2026, 7, 4),
        )
    )

    assert result.id == "loan-1"
    assert result.reservation_id == CANONICAL_RESERVATION_ID
    uow.loans.get_by_reservation_id.assert_awaited_once_with(
        CANONICAL_RESERVATION_ID
    )
    uow.acquire_borrowing_fence.assert_not_awaited()
    uow.loans.get_active_loan_for_book.assert_not_awaited()
    uow.loans.add.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_loan_enforces_authoritative_patron_tier_limit():
    uow = _uow("loans")
    uow.loans.get_by_reservation_id.return_value = None
    uow.loans.count_outstanding_for_patron.return_value = 5
    handler = _create_loan_handler(uow)

    with pytest.raises(PatronBorrowingLimitReachedException):
        await handler.handle(
            CreateLoanCommand(
                reservation_id=RESERVATION_ID,
                reservation_generation=3,
                patron_id="patron-1",
                patron_email="patron@example.com",
                catalog_book_id="book-1",
                book_title="Domain-Driven Design",
                borrowed_at=datetime(2026, 7, 4),
            )
        )

    uow.acquire_borrowing_fence.assert_awaited_once_with("patron-1")
    uow.loans.get_active_loan_for_book.assert_not_awaited()
    uow.loans.add.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_loan_rejects_token_reuse_with_different_facts():
    uow = _uow("loans")
    existing = MagicMock()
    existing.id.value = "loan-1"
    existing.reservation_id.value = RESERVATION_ID
    existing.reservation_generation = 3
    existing.patron_id = "different-patron"
    existing.patron_email = "patron@example.com"
    existing.catalog_book_id = "book-1"
    existing.book_title = "Domain-Driven Design"
    existing.borrowed_at = datetime(2026, 7, 4)
    existing.due_date.value = datetime(2026, 7, 18)
    uow.loans.get_by_reservation_id.return_value = existing
    handler = _create_loan_handler(uow)

    with pytest.raises(ReservationCorrelationMismatchException, match="patron_id"):
        await handler.handle(
            CreateLoanCommand(
                reservation_id=RESERVATION_ID,
                reservation_generation=3,
                patron_id="patron-1",
                patron_email="patron@example.com",
                catalog_book_id="book-1",
                book_title="Domain-Driven Design",
                borrowed_at=datetime(2026, 7, 4),
            )
        )

    uow.loans.get_active_loan_for_book.assert_not_awaited()
    uow.loans.add.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_duplicate_insert_recovers_by_exact_reservation():
    uow = _uow("loans")
    winner = MagicMock()
    winner.id.value = "loan-winner"
    winner.reservation_id.value = RESERVATION_ID
    winner.reservation_generation = 3
    winner.patron_id = "patron-1"
    winner.patron_email = "patron@example.com"
    winner.catalog_book_id = "book-1"
    winner.book_title = "Domain-Driven Design"
    winner.borrowed_at = datetime(2026, 7, 4)
    winner.due_date.value = datetime(2026, 7, 18)
    uow.loans.get_by_reservation_id.side_effect = [None, None, winner]
    uow.loans.get_active_loan_for_book.return_value = None
    uow.commit.side_effect = ConcurrentLoanCreationException(
        RESERVATION_ID, "book-1"
    )
    handler = _create_loan_handler(uow)

    result = await handler.handle(
        CreateLoanCommand(
            reservation_id=RESERVATION_ID,
            reservation_generation=3,
            patron_id="patron-1",
            patron_email="patron@example.com",
            catalog_book_id="book-1",
            book_title="Domain-Driven Design",
            borrowed_at=datetime(2026, 7, 4),
        )
    )

    assert result.id == "loan-winner"
    assert uow.__aenter__.await_count == 2
    assert uow.loans.get_active_loan_for_book.await_count == 1


@pytest.mark.asyncio
async def test_waiting_on_patron_fence_rechecks_reservation_before_contention():
    uow = _uow("loans")
    trace = []
    winner = MagicMock()
    winner.id.value = "loan-winner"
    winner.reservation_id.value = RESERVATION_ID
    winner.reservation_generation = 3
    winner.patron_id = "patron-1"
    winner.patron_email = "patron@example.com"
    winner.catalog_book_id = "book-1"
    winner.book_title = "Domain-Driven Design"
    winner.borrowed_at = datetime(2026, 7, 4)
    winner.due_date.value = datetime(2026, 7, 18)
    reservations = iter((None, winner))

    async def get_reservation(_reservation_id):
        trace.append("reservation")
        return next(reservations)

    async def acquire_fence(_patron_id):
        trace.append("fence")

    async def count_outstanding(_patron_id):
        trace.append("count")
        return 0

    uow.loans.get_by_reservation_id.side_effect = get_reservation
    uow.acquire_borrowing_fence.side_effect = acquire_fence
    uow.loans.count_outstanding_for_patron.side_effect = count_outstanding
    handler = _create_loan_handler(uow)

    result = await handler.handle(
        CreateLoanCommand(
            reservation_id=RESERVATION_ID,
            reservation_generation=3,
            patron_id="patron-1",
            patron_email="patron@example.com",
            catalog_book_id="book-1",
            book_title="Domain-Driven Design",
            borrowed_at=datetime(2026, 7, 4),
        )
    )

    assert result.id == "loan-winner"
    uow.acquire_borrowing_fence.assert_awaited_once_with("patron-1")
    assert trace == ["reservation", "fence", "count", "reservation"]
    uow.loans.get_active_loan_for_book.assert_not_awaited()
    uow.loans.add.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_loan_rejects_same_token_with_mismatched_correlation():
    uow = _uow("loans")
    loan = MagicMock()
    loan.id.value = "loan-1"
    loan.reservation_id.value = CANONICAL_RESERVATION_ID
    loan.reservation_generation = 4
    loan.patron_id = "patron-1"
    loan.catalog_book_id = "book-1"
    uow.loans.get_by_reservation_id.return_value = loan
    handler = CancelLoanHandler(uow, logger=MagicMock())

    with pytest.raises(ReservationCorrelationMismatchException):
        await handler.handle(
            CancelLoanCommand(
                reservation_id=CANONICAL_RESERVATION_ID.upper(),
                reservation_generation=3,
                patron_id="patron-1",
                catalog_book_id="book-1",
                expected_loan_id="loan-1",
                reason="stale reservation",
            )
        )

    loan.cancel.assert_not_called()
    uow.loans.update.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_loan_rejects_mismatched_expected_loan_identity():
    uow = _uow("loans")
    loan = MagicMock()
    loan.id.value = "loan-current"
    loan.reservation_id.value = CANONICAL_RESERVATION_ID
    loan.reservation_generation = 3
    loan.patron_id = "patron-1"
    loan.catalog_book_id = "book-1"
    uow.loans.get_by_reservation_id.return_value = loan
    handler = CancelLoanHandler(uow, logger=MagicMock())

    with pytest.raises(ReservationCorrelationMismatchException):
        await handler.handle(
            CancelLoanCommand(
                reservation_id=CANONICAL_RESERVATION_ID,
                reservation_generation=3,
                patron_id="patron-1",
                catalog_book_id="book-1",
                expected_loan_id="loan-stale",
                reason="stale confirmation",
            )
        )

    loan.cancel.assert_not_called()
    uow.loans.update.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_loan_commits_exact_matching_compensation():
    uow = _uow("loans")
    loan = MagicMock()
    loan.id.value = "loan-1"
    loan.reservation_id.value = CANONICAL_RESERVATION_ID
    loan.reservation_generation = 3
    loan.patron_id = "patron-1"
    loan.catalog_book_id = "book-1"
    loan.cancel.return_value = True
    uow.loans.get_by_reservation_id.return_value = loan
    handler = CancelLoanHandler(uow, logger=MagicMock())

    changed = await handler.handle(
        CancelLoanCommand(
            reservation_id=CANONICAL_RESERVATION_ID.upper(),
            reservation_generation=3,
            patron_id="patron-1",
            catalog_book_id="book-1",
            expected_loan_id=None,
            reason="reservation expired",
        )
    )

    assert changed is True
    uow.loans.get_by_reservation_id.assert_awaited_once_with(
        CANONICAL_RESERVATION_ID
    )
    loan.cancel.assert_called_once_with("reservation expired")
    uow.loans.update.assert_awaited_once_with(loan)
    uow.commit.assert_awaited_once()

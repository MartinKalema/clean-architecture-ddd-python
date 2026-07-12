"""Unit tests for application-layer borrow/return choreography."""
from dataclasses import replace
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.command_handlers.create_loan import CreateLoanResult
from src.application.event_handlers import (
    CancelLoanOnBookReleasedHandler,
    ConfirmBorrowOnLoanCreatedHandler,
    CreateLoanOnBookReservedHandler,
    ReturnBookOnLoanCompletedHandler,
    SendLoanConfirmationEmailHandler,
)
from src.domain.catalog import (
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
    LoanCorrelationMismatchException,
    StaleLoanCompletionException,
    StaleReservationException,
)
from src.domain.lending import LoanCompleted, LoanCreated
from src.domain.lending.exceptions import (
    BookNotAvailableException,
    PatronBorrowingLimitReachedException,
    PatronNotEligibleForLoanException,
)
from src.application.ports import EmailDeliveryException


RESERVATION_ID = "11111111-1111-4111-8111-111111111111"


def _book_reserved() -> CatalogBookReserved:
    return CatalogBookReserved(
        book_id="book-1",
        title="Domain-Driven Design",
        reservation_id=RESERVATION_ID,
        reservation_generation=3,
        patron_id="patron-1",
        reserved_at=datetime(2026, 7, 4, 12, 0),
        borrower_email="patron@example.com",
    )


def _loan_created() -> LoanCreated:
    return LoanCreated(
        loan_id="loan-1",
        reservation_id=RESERVATION_ID,
        reservation_generation=3,
        patron_id="patron-1",
        patron_email="patron@example.com",
        book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )


def _book_borrowed() -> CatalogBookBorrowed:
    return CatalogBookBorrowed(
        book_id="book-1",
        title="Domain-Driven Design",
        reservation_id=RESERVATION_ID,
        reservation_generation=3,
        patron_id="patron-1",
        loan_id="loan-1",
        borrower_email="patron@example.com",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        return_due_date=datetime(2026, 7, 18, 12, 0),
    )


def _book_released() -> CatalogBookReleased:
    return CatalogBookReleased(
        book_id="book-1",
        reservation_id=RESERVATION_ID,
        reservation_generation=3,
        patron_id="patron-1",
        reason="reservation expired",
    )


def _loan_completed() -> LoanCompleted:
    return LoanCompleted(
        loan_id="loan-1",
        reservation_id=RESERVATION_ID,
        reservation_generation=3,
        patron_id="patron-1",
        book_id="book-1",
        returned_at=datetime(2026, 7, 10, 12, 0),
        was_overdue=False,
    )


def _reserved_handler():
    create_loan_handler = AsyncMock()
    create_loan_handler.handle.return_value = CreateLoanResult(
        id="loan-1",
        reservation_id=RESERVATION_ID,
        reservation_generation=3,
        patron_id="patron-1",
        catalog_book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )
    release_handler = AsyncMock()
    handler = CreateLoanOnBookReservedHandler(
        create_loan_handler=create_loan_handler,
        release_book_reservation_handler=release_handler,
        logger=MagicMock(),
    )
    return handler, create_loan_handler, release_handler


class TestCreateLoanOnBookReserved:
    @pytest.mark.asyncio
    async def test_creates_loan_with_exact_reservation_correlation(self):
        handler, create_loan, release = _reserved_handler()

        await handler.handle(_book_reserved())

        command = create_loan.handle.await_args.args[0]
        assert command.reservation_id == RESERVATION_ID
        assert command.reservation_generation == 3
        assert command.patron_id == "patron-1"
        assert command.patron_email == "patron@example.com"
        assert command.catalog_book_id == "book-1"
        assert command.book_title == "Domain-Driven Design"
        assert command.borrowed_at == datetime(2026, 7, 4, 12, 0)
        release.handle.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error",
        [
            BookNotAvailableException("book-1"),
            PatronBorrowingLimitReachedException("patron-1", 5),
            PatronNotEligibleForLoanException("patron-1", "suspended"),
        ],
    )
    async def test_authoritative_permanent_rejection_releases_exact_reservation(
        self, error
    ):
        handler, create_loan, release = _reserved_handler()
        create_loan.handle.side_effect = error

        await handler.handle(_book_reserved())

        command = release.handle.await_args.args[0]
        assert command.book_id == "book-1"
        assert command.reservation_id == RESERVATION_ID
        assert command.reservation_generation == 3
        assert command.patron_id == "patron-1"

    @pytest.mark.asyncio
    async def test_unexpected_failure_propagates_without_compensation(self):
        handler, create_loan, release = _reserved_handler()
        create_loan.handle.side_effect = RuntimeError("database down")

        with pytest.raises(RuntimeError, match="database down"):
            await handler.handle(_book_reserved())

        release.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_compensation_is_acknowledged(self):
        handler, create_loan, release = _reserved_handler()
        create_loan.handle.side_effect = BookNotAvailableException("book-1")
        release.handle.side_effect = StaleReservationException(
            "book-1", RESERVATION_ID, 3, "release reservation"
        )

        await handler.handle(_book_reserved())

        handler.logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_transient_compensation_failure_propagates_for_retry(self):
        handler, create_loan, release = _reserved_handler()
        create_loan.handle.side_effect = BookNotAvailableException("book-1")
        release.handle.side_effect = RuntimeError("catalog down")

        with pytest.raises(RuntimeError, match="catalog down"):
            await handler.handle(_book_reserved())


class TestConfirmBorrowOnLoanCreated:
    @pytest.mark.asyncio
    async def test_confirms_the_exact_reservation_and_loan(self):
        confirm = AsyncMock()
        cancel = AsyncMock()
        handler = ConfirmBorrowOnLoanCreatedHandler(
            confirm, cancel, logger=MagicMock()
        )

        await handler.handle(_loan_created())

        command = confirm.handle.await_args.args[0]
        assert command.book_id == "book-1"
        assert command.reservation_id == RESERVATION_ID
        assert command.reservation_generation == 3
        assert command.patron_id == "patron-1"
        assert command.loan_id == "loan-1"
        cancel.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stale_confirmation_cancels_only_its_tentative_loan(self):
        confirm = AsyncMock()
        confirm.handle.side_effect = StaleReservationException(
            "book-1", RESERVATION_ID, 3, "confirm borrow"
        )
        cancel = AsyncMock()
        handler = ConfirmBorrowOnLoanCreatedHandler(
            confirm, cancel, logger=MagicMock()
        )

        await handler.handle(_loan_created())

        command = cancel.handle.await_args.args[0]
        assert command.reservation_id == RESERVATION_ID
        assert command.reservation_generation == 3
        assert command.patron_id == "patron-1"
        assert command.expected_loan_id == "loan-1"

    @pytest.mark.asyncio
    async def test_unexpected_confirmation_failure_propagates_for_retry(self):
        confirm = AsyncMock()
        confirm.handle.side_effect = RuntimeError("database down")
        cancel = AsyncMock()
        handler = ConfirmBorrowOnLoanCreatedHandler(
            confirm, cancel, logger=MagicMock()
        )

        with pytest.raises(RuntimeError, match="database down"):
            await handler.handle(_loan_created())

        cancel.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_stale_loan_cancellation_propagates_for_retry(self):
        confirm = AsyncMock()
        confirm.handle.side_effect = StaleReservationException(
            "book-1", RESERVATION_ID, 3, "confirm borrow"
        )
        cancel = AsyncMock()
        cancel.handle.side_effect = RuntimeError("lending down")
        handler = ConfirmBorrowOnLoanCreatedHandler(
            confirm, cancel, logger=MagicMock()
        )

        with pytest.raises(RuntimeError, match="lending down"):
            await handler.handle(_loan_created())


class TestCatalogReleaseReaction:
    @pytest.mark.asyncio
    async def test_cancels_matching_reservation_loan(self):
        cancel = AsyncMock()
        cancel.handle.return_value = True
        handler = CancelLoanOnBookReleasedHandler(cancel, logger=MagicMock())

        await handler.handle(_book_released())

        command = cancel.handle.await_args.args[0]
        assert command.reservation_id == RESERVATION_ID
        assert command.reservation_generation == 3
        assert command.patron_id == "patron-1"
        assert command.catalog_book_id == "book-1"
        assert command.expected_loan_id is None
        assert command.reason == "reservation expired"


class TestLoanCompletedReaction:
    @pytest.mark.asyncio
    async def test_returns_catalog_book_for_exact_loan(self):
        return_book = AsyncMock()
        handler = ReturnBookOnLoanCompletedHandler(
            return_book, logger=MagicMock()
        )

        await handler.handle(_loan_completed())

        command = return_book.handle.await_args.args[0]
        assert command.book_id == "book-1"
        assert command.loan_id == "loan-1"
        assert command.reservation_id == RESERVATION_ID
        assert command.reservation_generation == 3
        assert command.patron_id == "patron-1"

    @pytest.mark.asyncio
    async def test_stale_completion_is_acknowledged(self):
        return_book = AsyncMock()
        return_book.handle.side_effect = StaleLoanCompletionException(
            "book-1", "loan-1"
        )
        handler = ReturnBookOnLoanCompletedHandler(
            return_book, logger=MagicMock()
        )

        await handler.handle(_loan_completed())

        handler.logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_current_loan_correlation_conflict_is_not_acknowledged(self):
        return_book = AsyncMock()
        return_book.handle.side_effect = LoanCorrelationMismatchException(
            "book-1", "loan-1", "reservation_id differs"
        )
        handler = ReturnBookOnLoanCompletedHandler(
            return_book, logger=MagicMock()
        )

        with pytest.raises(LoanCorrelationMismatchException):
            await handler.handle(_loan_completed())

    @pytest.mark.asyncio
    async def test_transient_return_failure_propagates_for_retry(self):
        return_book = AsyncMock()
        return_book.handle.side_effect = RuntimeError("catalog down")
        handler = ReturnBookOnLoanCompletedHandler(
            return_book, logger=MagicMock()
        )

        with pytest.raises(RuntimeError, match="catalog down"):
            await handler.handle(_loan_completed())


class TestSendLoanConfirmationEmail:
    @pytest.mark.asyncio
    async def test_definitive_catalog_borrow_sends_confirmation_email(self):
        email_service = AsyncMock()
        handler = SendLoanConfirmationEmailHandler(
            email_service, logger=MagicMock()
        )
        event = _book_borrowed()

        await handler.handle(event)

        email_service.send_email.assert_awaited_once()
        kwargs = email_service.send_email.await_args.kwargs
        assert kwargs["to_email"] == "patron@example.com"
        assert kwargs["delivery_id"] == event.event_id
        assert "Domain-Driven Design" in kwargs["subject"]
        assert "2026-07-18" in kwargs["content"]

    @pytest.mark.asyncio
    async def test_catalog_text_is_escaped_and_cannot_inject_headers(self):
        email_service = AsyncMock()
        handler = SendLoanConfirmationEmailHandler(
            email_service, logger=MagicMock()
        )
        event = replace(
            _book_borrowed(),
            title='<img src=x onerror="alert(1)">\r\nBcc: victim@example.com',
        )

        await handler.handle(event)

        kwargs = email_service.send_email.await_args.kwargs
        assert "\r" not in kwargs["subject"]
        assert "\n" not in kwargs["subject"]
        assert "<img" not in kwargs["content"]
        assert "&lt;img" in kwargs["content"]

    @pytest.mark.asyncio
    async def test_permanent_rejection_is_parked_for_operator_replay(self):
        email_service = AsyncMock()
        email_service.send_email.side_effect = EmailDeliveryException(
            "401 Unauthorized"
        )
        handler = SendLoanConfirmationEmailHandler(
            email_service, logger=MagicMock()
        )

        with pytest.raises(EmailDeliveryException):
            await handler.handle(_book_borrowed())

        handler.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_transient_failure_propagates_for_retry(self):
        email_service = AsyncMock()
        email_service.send_email.side_effect = TimeoutError("slow SendGrid")
        handler = SendLoanConfirmationEmailHandler(
            email_service, logger=MagicMock()
        )

        with pytest.raises(TimeoutError):
            await handler.handle(_book_borrowed())

"""
Unit tests for application-layer event handlers.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.command_handlers.create_loan import CreateLoanResult
from src.application.query_handlers import PatronReadModel
from src.application.event_handlers import (
    ConfirmBorrowOnLoanCreatedHandler,
    CreateLoanOnBookReservedHandler,
    SendLoanConfirmationEmailHandler,
)
from src.domain.catalog import CatalogBookReserved
from src.domain.lending import LoanCreated
from src.domain.lending.exceptions import BookNotAvailableException
from src.domain.shared_kernel import EmailDeliveryException


def _patron_read_model(patron_id="patron-1", is_suspended=False):
    return PatronReadModel(
        id=patron_id, name="Test Patron", first_name="Test", last_name="Patron",
        email="patron@example.com", membership_tier="regular",
        is_suspended=is_suspended, suspended_reason=None,
        registered_at=datetime(2026, 1, 1),
    )


def _book_reserved() -> CatalogBookReserved:
    return CatalogBookReserved(
        book_id="book-1",
        title="Domain-Driven Design",
        reserved_at=datetime(2026, 7, 4, 12, 0),
        return_due_date=datetime(2026, 7, 18, 12, 0),
        borrower_email="patron@example.com",
    )


def _loan_created() -> LoanCreated:
    return LoanCreated(
        loan_id="loan-1",
        patron_id="patron-1",
        patron_email="patron@example.com",
        book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )


def _reserved_handler(patron=...):
    create_loan_handler = AsyncMock()
    create_loan_handler.handle.return_value = CreateLoanResult(
        id="loan-1",
        patron_id="patron-1",
        catalog_book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )
    release_handler = AsyncMock()
    patron_repository = AsyncMock()
    patron_repository.find_by_email.return_value = (
        _patron_read_model() if patron is ... else patron
    )
    handler = CreateLoanOnBookReservedHandler(
        create_loan_handler=create_loan_handler,
        release_book_reservation_handler=release_handler,
        patron_query_repository=patron_repository,
        logger=MagicMock(),
    )
    return handler, create_loan_handler, release_handler


class TestCreateLoanOnBookReserved:
    @pytest.mark.asyncio
    async def test_creates_loan_with_catalog_due_date(self):
        handler, create_loan, release = _reserved_handler()

        await handler.handle(_book_reserved())

        command = create_loan.handle.await_args.args[0]
        assert command.patron_id == "patron-1"
        assert command.patron_email == "patron@example.com"
        assert command.catalog_book_id == "book-1"
        assert command.book_title == "Domain-Driven Design"
        assert command.loan_duration_days == 14  # honors the catalog's due date
        assert command.borrowed_at == datetime(2026, 7, 4, 12, 0)
        release.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_patron_compensates_by_releasing_reservation(self):
        handler, create_loan, release = _reserved_handler(patron=None)

        await handler.handle(_book_reserved())

        create_loan.handle.assert_not_awaited()
        release.handle.assert_awaited_once()
        assert release.handle.await_args.args[0].book_id == "book-1"

    @pytest.mark.asyncio
    async def test_suspended_patron_compensates_by_releasing_reservation(self):
        handler, create_loan, release = _reserved_handler(
            patron=_patron_read_model(is_suspended=True)
        )

        await handler.handle(_book_reserved())

        create_loan.handle.assert_not_awaited()
        release.handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redelivered_event_is_idempotent_not_compensated(self):
        handler, create_loan, release = _reserved_handler()
        create_loan.handle.side_effect = BookNotAvailableException("book-1")

        await handler.handle(_book_reserved())

        # Existing active loan means the reservation already succeeded:
        # releasing would give away a legitimately held book
        release.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_loan_creation_failure_compensates(self):
        handler, create_loan, release = _reserved_handler()
        create_loan.handle.side_effect = RuntimeError("db down")

        await handler.handle(_book_reserved())

        release.handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_compensation_is_reraised_for_retry(self):
        handler, create_loan, release = _reserved_handler(patron=None)
        release.handle.side_effect = RuntimeError("catalog down")

        # A transiently-failed compensation must trigger redelivery, not
        # silent loss (the reaper is only the final backstop)
        with pytest.raises(RuntimeError):
            await handler.handle(_book_reserved())

        handler.logger.error.assert_called_once()


class TestConfirmBorrowOnLoanCreated:
    @pytest.mark.asyncio
    async def test_confirms_with_the_loan_timestamps(self):
        confirm = AsyncMock()
        handler = ConfirmBorrowOnLoanCreatedHandler(confirm, logger=MagicMock())

        await handler.handle(_loan_created())

        command = confirm.handle.await_args.args[0]
        assert command.book_id == "book-1"
        assert command.borrower_email == "patron@example.com"
        assert command.borrowed_at == datetime(2026, 7, 4, 12, 0)
        assert command.return_due_date == datetime(2026, 7, 18, 12, 0)

    @pytest.mark.asyncio
    async def test_unexpected_failure_propagates_for_retry(self):
        confirm = AsyncMock()
        confirm.handle.side_effect = RuntimeError("db down")
        handler = ConfirmBorrowOnLoanCreatedHandler(confirm, logger=MagicMock())

        with pytest.raises(RuntimeError):
            await handler.handle(_loan_created())


class TestSendLoanConfirmationEmail:
    @pytest.mark.asyncio
    async def test_loan_created_sends_confirmation_email(self):
        email_service = AsyncMock()
        handler = SendLoanConfirmationEmailHandler(email_service, logger=MagicMock())

        await handler.handle(_loan_created())

        email_service.send_email.assert_awaited_once()
        kwargs = email_service.send_email.await_args.kwargs
        assert kwargs["to_email"] == "patron@example.com"
        assert "Domain-Driven Design" in kwargs["subject"]
        assert "2026-07-18" in kwargs["content"]

    @pytest.mark.asyncio
    async def test_permanent_rejection_is_escalated_not_retried(self):
        email_service = AsyncMock()
        email_service.send_email.side_effect = EmailDeliveryException("401 Unauthorized")
        handler = SendLoanConfirmationEmailHandler(email_service, logger=MagicMock())

        # Must not raise: retrying a permanent rejection would head-of-line
        # block the pipeline without ever succeeding
        await handler.handle(_loan_created())

        handler.logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_transient_failure_propagates_for_retry(self):
        email_service = AsyncMock()
        email_service.send_email.side_effect = TimeoutError("slow SendGrid")
        handler = SendLoanConfirmationEmailHandler(email_service, logger=MagicMock())

        with pytest.raises(TimeoutError):
            await handler.handle(_loan_created())

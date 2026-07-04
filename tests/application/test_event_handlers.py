"""
Unit tests for application-layer event handlers.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.command_handlers.create_loan import CreateLoanResult
from src.application.event_handlers import (
    CreateLoanOnBookBorrowedHandler,
    SendLoanConfirmationEmailHandler,
)
from src.domain.catalog import CatalogBookBorrowed
from src.domain.lending import LoanCreated
from src.domain.lending.exceptions import BookNotAvailableException


def _book_borrowed() -> CatalogBookBorrowed:
    return CatalogBookBorrowed(
        book_id="book-1",
        title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        return_due_date=datetime(2026, 7, 18, 12, 0),
        borrower_email="patron@example.com",
    )


def _handler(patron=...):
    create_loan_handler = AsyncMock()
    create_loan_handler.handle.return_value = CreateLoanResult(
        id="loan-1",
        patron_id="patron-1",
        catalog_book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )
    return_book_handler = AsyncMock()
    patron_repository = AsyncMock()
    patron_repository.find_by_email.return_value = (
        {"id": "patron-1", "is_suspended": False} if patron is ... else patron
    )
    handler = CreateLoanOnBookBorrowedHandler(
        create_loan_handler=create_loan_handler,
        return_book_handler=return_book_handler,
        patron_query_repository=patron_repository,
        logger=MagicMock(),
    )
    return handler, create_loan_handler, return_book_handler


class TestCreateLoanOnBookBorrowed:
    @pytest.mark.asyncio
    async def test_creates_loan_with_catalog_due_date(self):
        handler, create_loan, return_book = _handler()

        await handler.handle(_book_borrowed())

        command = create_loan.handle.await_args.args[0]
        assert command.patron_id == "patron-1"
        assert command.patron_email == "patron@example.com"
        assert command.catalog_book_id == "book-1"
        assert command.book_title == "Domain-Driven Design"
        assert command.loan_duration_days == 14  # honors the catalog's due date
        return_book.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_patron_compensates_by_returning_book(self):
        handler, create_loan, return_book = _handler(patron=None)

        await handler.handle(_book_borrowed())

        create_loan.handle.assert_not_awaited()
        return_book.handle.assert_awaited_once()
        assert return_book.handle.await_args.args[0].book_id == "book-1"

    @pytest.mark.asyncio
    async def test_suspended_patron_compensates_by_returning_book(self):
        handler, create_loan, return_book = _handler(
            patron={"id": "patron-1", "is_suspended": True}
        )

        await handler.handle(_book_borrowed())

        create_loan.handle.assert_not_awaited()
        return_book.handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_redelivered_event_is_idempotent_not_compensated(self):
        handler, create_loan, return_book = _handler()
        create_loan.handle.side_effect = BookNotAvailableException("book-1")

        await handler.handle(_book_borrowed())

        # Existing active loan means the borrow already succeeded:
        # compensating would return a legitimately borrowed book
        return_book.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_loan_creation_failure_compensates(self):
        handler, create_loan, return_book = _handler()
        create_loan.handle.side_effect = RuntimeError("db down")

        await handler.handle(_book_borrowed())

        return_book.handle.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_compensation_is_escalated_not_raised(self):
        handler, create_loan, return_book = _handler(patron=None)
        return_book.handle.side_effect = RuntimeError("catalog down")

        await handler.handle(_book_borrowed())  # must not raise

        handler.logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_loan_created_sends_confirmation_email():
    email_service = AsyncMock()
    handler = SendLoanConfirmationEmailHandler(email_service, logger=MagicMock())

    event = LoanCreated(
        loan_id="loan-1",
        patron_id="patron-1",
        patron_email="patron@example.com",
        book_id="book-1",
        book_title="Clean Architecture",
        borrowed_at=datetime(2026, 7, 4, 12, 0),
        due_date=datetime(2026, 7, 18, 12, 0),
    )

    await handler.handle(event)

    email_service.send_email.assert_awaited_once()
    kwargs = email_service.send_email.await_args.kwargs
    assert kwargs["to_email"] == "patron@example.com"
    assert "Clean Architecture" in kwargs["subject"]
    assert "2026-07-18" in kwargs["content"]

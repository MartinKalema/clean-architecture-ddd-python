"""Application-level guarantees for retry-safe HTTP commands."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.command_handlers.add_book import AddBookCommand, AddBookHandler
from src.application.command_handlers.borrow_book import BorrowBookCommand, BorrowBookHandler
from src.application.command_handlers.return_loan import (
    ReturnLoanCommand,
    ReturnLoanHandler,
)
from src.application.command_handlers.suspend_patron import (
    SuspendPatronCommand,
    SuspendPatronHandler,
)
from src.application.exceptions import (
    IdempotencyKeyConflictException,
    InvalidIdempotencyKeyException,
)
from src.application.ports import CommandReceipt, IdempotencyKey, command_fingerprint


def _uow():
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.books = AsyncMock()
    uow.command_receipts = AsyncMock()
    uow.borrow_operations = AsyncMock()
    uow.commit = AsyncMock()
    return uow


class _Clock:
    def now(self):
        return datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


def test_malformed_idempotency_key_is_validation_not_a_reuse_conflict():
    with pytest.raises(InvalidIdempotencyKeyException):
        IdempotencyKey("!!!!!!!!")


@pytest.mark.asyncio
async def test_add_book_replay_returns_original_identity_without_second_write():
    uow = _uow()
    response = {
        "id": "book-original",
        "title": "Clean Architecture",
        "author": "Robert C. Martin",
        "is_borrowed": False,
        "status": "available",
    }
    uow.command_receipts.get.return_value = CommandReceipt(
        scope="catalog.add_book",
        idempotency_key="add-book-001",
        request_hash=command_fingerprint(
            {"title": response["title"], "author": response["author"]}
        ),
        response=response,
    )

    result = await AddBookHandler(uow, MagicMock()).handle(
        AddBookCommand(
            title="  Clean   Architecture ",
            author="Robert C. Martin",
            idempotency_key="add-book-001",
        )
    )

    assert result.id == "book-original"
    uow.books.add.assert_not_awaited()
    uow.command_receipts.add.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_idempotency_key_rejects_different_command_facts():
    uow = _uow()
    uow.command_receipts.get.return_value = CommandReceipt(
        scope="catalog.add_book",
        idempotency_key="add-book-002",
        request_hash=command_fingerprint(
            {"title": "Original", "author": "Original Author"}
        ),
        response={},
    )

    with pytest.raises(IdempotencyKeyConflictException):
        await AddBookHandler(uow, MagicMock()).handle(
            AddBookCommand(
                title="Different",
                author="Original Author",
                idempotency_key="add-book-002",
            )
        )

    uow.books.add.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_borrow_replay_recovers_original_operation_without_rechecking_patron():
    uow = _uow()
    response = {
        "id": "book-1",
        "title": "DDD",
        "author": "Eric Evans",
        "is_borrowed": False,
        "reservation_id": "11111111-1111-4111-8111-111111111111",
        "reservation_generation": 4,
        "operation_id": "11111111-1111-4111-8111-111111111111",
        "status": "reserved",
        "return_due_date": None,
    }
    uow.command_receipts.get.return_value = CommandReceipt(
        scope="catalog.borrow_book",
        idempotency_key="borrow-book-001",
        request_hash=command_fingerprint(
            {"book_id": "book-1", "borrower_email": "patron@example.com"}
        ),
        response=response,
    )
    directory = AsyncMock()

    result = await BorrowBookHandler(
        uow, directory, MagicMock(), _Clock()
    ).handle(
        BorrowBookCommand(
            book_id="book-1",
            borrower_email="PATRON@example.com",
            idempotency_key="borrow-book-001",
        )
    )

    assert result.operation_id == response["operation_id"]
    directory.find_by_email.assert_not_awaited()
    uow.books.get_by_id.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_patron_state_replay_returns_committed_write_snapshot():
    uow = _uow()
    uow.patrons = AsyncMock()
    registered_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    response = {
        "id": "patron-1",
        "name": "Ada Lovelace",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "membership_tier": "regular",
        "is_suspended": True,
        "suspended_reason": "late returns",
        "registered_at": registered_at.isoformat(),
    }
    uow.command_receipts.get.return_value = CommandReceipt(
        scope="patron.suspend",
        idempotency_key="suspend-patron-001",
        request_hash=command_fingerprint(
            {"patron_id": "patron-1", "reason": "late returns"}
        ),
        response=response,
    )

    result = await SuspendPatronHandler(uow, MagicMock()).handle(
        SuspendPatronCommand(
            patron_id="patron-1",
            reason=" late   returns ",
            idempotency_key="suspend-patron-001",
        )
    )

    assert result.registered_at == registered_at
    uow.patrons.get_by_id.assert_not_awaited()
    uow.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_return_replay_does_not_return_or_emit_a_second_completion():
    uow = _uow()
    uow.loans = AsyncMock()
    returned_at = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    uow.command_receipts.get.return_value = CommandReceipt(
        scope="lending.return_loan",
        idempotency_key="return-loan-001",
        request_hash=command_fingerprint({"loan_id": "loan-1"}),
        response={
            "id": "loan-1",
            "returned_at": returned_at.isoformat(),
            "was_overdue": False,
        },
    )

    result = await ReturnLoanHandler(
        uow,
        MagicMock(),
        _Clock(),
    ).handle(
        ReturnLoanCommand(
            loan_id="loan-1",
            idempotency_key="return-loan-001",
        )
    )

    assert result.returned_at == returned_at
    uow.loans.get_by_id.assert_not_awaited()
    uow.commit.assert_not_awaited()

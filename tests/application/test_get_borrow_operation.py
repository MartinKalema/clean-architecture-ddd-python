"""Workflow status is an explicit application query, not a command side-channel."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.exceptions import BorrowOperationNotFoundException
from src.application.ports import BorrowOperation, BorrowOperationStatus
from src.application.query_handlers import (
    GetBorrowOperationHandler,
    GetBorrowOperationQuery,
)


def _uow(operation):
    uow = MagicMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=None)
    uow.borrow_operations = AsyncMock()
    uow.borrow_operations.get.return_value = operation
    return uow


@pytest.mark.asyncio
async def test_get_borrow_operation_returns_durable_process_state():
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    operation = BorrowOperation(
        operation_id="11111111-1111-4111-8111-111111111111",
        book_id="book-1",
        patron_id="patron-1",
        reservation_generation=2,
        status=BorrowOperationStatus.BORROWED,
        loan_id="loan-1",
        created_at=now,
        updated_at=now,
    )

    result = await GetBorrowOperationHandler(_uow(operation)).handle(
        GetBorrowOperationQuery(operation.operation_id)
    )

    assert result.status == "borrowed"
    assert result.loan_id == "loan-1"


@pytest.mark.asyncio
async def test_unknown_borrow_operation_is_not_found():
    with pytest.raises(BorrowOperationNotFoundException):
        await GetBorrowOperationHandler(_uow(None)).handle(
            GetBorrowOperationQuery("missing-operation")
        )

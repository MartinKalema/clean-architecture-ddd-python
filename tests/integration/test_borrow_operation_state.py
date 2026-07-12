"""Durable borrow workflow state is fenced as strictly as the aggregates."""
from datetime import datetime, timezone

import pytest

from src.application.exceptions import BorrowOperationTransitionException
from src.application.ports import BorrowOperationStatus
from src.infrastructure.adapters.application_state.borrow_operation_repository import (
    BorrowOperationRepository,
)
from src.infrastructure.adapters.application_state.models import BorrowOperationModel


OPERATION_ID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.asyncio
async def test_operation_rejects_status_skip_and_wrong_fencing_generation(db_session):
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    db_session.add(
        BorrowOperationModel(
            operation_id=OPERATION_ID,
            book_id="book-1",
            patron_id="patron-1",
            reservation_generation=3,
            status="reserved",
            loan_id=None,
            failure_reason=None,
            created_at=now,
            updated_at=now,
        )
    )
    await db_session.flush()
    repository = BorrowOperationRepository(db_session)

    with pytest.raises(BorrowOperationTransitionException):
        await repository.transition(
            OPERATION_ID,
            BorrowOperationStatus.RETURNED,
            book_id="book-1",
            patron_id="patron-1",
            reservation_generation=3,
            loan_id="loan-1",
            updated_at=now,
        )

    with pytest.raises(BorrowOperationTransitionException):
        await repository.transition(
            OPERATION_ID,
            BorrowOperationStatus.BORROWED,
            book_id="book-1",
            patron_id="patron-1",
            reservation_generation=4,
            loan_id="loan-1",
            updated_at=now,
        )

    await repository.transition(
        OPERATION_ID,
        BorrowOperationStatus.BORROWED,
        book_id="book-1",
        patron_id="patron-1",
        reservation_generation=3,
        loan_id="loan-1",
        updated_at=now,
    )
    assert (await repository.get(OPERATION_ID)).status is BorrowOperationStatus.BORROWED

"""
Integration tests for the transactional outbox.

Verifies that units of work stage domain events into the outbox table in
the same transaction as the aggregate changes.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.command_handlers.create_loan import (
    CreateLoanCommand,
    CreateLoanHandler,
)
from src.application.ports import BorrowerProfile
from src.domain.lending import LoanCreated
from src.domain.lending.exceptions import BookNotAvailableException
from src.infrastructure.adapters.events import (
    deserialize_event,
    outbox_type_for_event_class,
)
from src.infrastructure.adapters.lending import LoanUnitOfWork
from src.infrastructure.adapters.outbox import OutboxMessageModel


async def _get_outbox_rows(test_db, event_class) -> list[OutboxMessageModel]:
    wire_type = outbox_type_for_event_class(event_class)
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel).where(OutboxMessageModel.type == wire_type)
        )
        return list(result.scalars().all())


def _borrower_directory():
    emails = {
        "patron-outbox-1": "outbox@example.com",
        "patron-outbox-2": "outbox2@example.com",
        "patron-outbox-3": "outbox3@example.com",
        "patron-outbox-4": "outbox4@example.com",
    }
    directory = AsyncMock()
    directory.get_by_id.side_effect = lambda patron_id: BorrowerProfile(
        patron_id=patron_id,
        email=emails[patron_id],
        is_eligible=True,
        membership_tier="regular",
    )
    return directory


@pytest.mark.asyncio
async def test_create_loan_writes_loan_created_to_outbox(test_db):
    """Committing a new loan stages a LoanCreated event in the outbox."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = LoanUnitOfWork(session_factory)
    handler = CreateLoanHandler(
        uow,
        borrower_directory=_borrower_directory(),
        logger=MagicMock(),
    )

    command = CreateLoanCommand(
        reservation_id="11111111-1111-4111-8111-111111111111",
        reservation_generation=1,
        patron_id="patron-outbox-1",
        patron_email="outbox@example.com",
        catalog_book_id="book-outbox-1",
        book_title="The Outbox Pattern",
        borrowed_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )
    result = await handler.handle(command)

    rows = await _get_outbox_rows(test_db, LoanCreated)
    rows = [r for r in rows if r.aggregateid == result.id]
    assert len(rows) == 1

    row = rows[0]
    assert row.aggregatetype == "loan"
    payload = json.loads(row.payload)
    assert payload["contract"] == {
        "namespace": "library.lending",
        "name": "loan-created",
        "version": 1,
    }
    assert payload["data"]["reservation_id"] == command.reservation_id
    assert payload["data"]["reservation_generation"] == 1
    assert payload["data"]["patron_email"] == "outbox@example.com"
    assert payload["data"]["book_title"] == "The Outbox Pattern"
    assert payload["metadata"]["event_id"] == row.id

    # The payload round-trips back into a typed domain event
    event = deserialize_event(payload)
    assert isinstance(event, LoanCreated)
    assert event.loan_id == result.id
    assert event.due_date == result.due_date


@pytest.mark.asyncio
async def test_committed_aggregate_has_no_pending_events(test_db):
    """Events are consumed by the outbox: none remain on the aggregate."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = LoanUnitOfWork(session_factory)
    handler = CreateLoanHandler(
        uow,
        borrower_directory=_borrower_directory(),
        logger=MagicMock(),
    )

    command = CreateLoanCommand(
        reservation_id="22222222-2222-4222-8222-222222222222",
        reservation_generation=1,
        patron_id="patron-outbox-2",
        patron_email="outbox2@example.com",
        catalog_book_id="book-outbox-2",
        book_title="Event Consumption",
        borrowed_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )
    result = await handler.handle(command)

    async with uow:
        loan = await uow.loans.get_by_id(result.id)
        assert loan.get_domain_events() == []


@pytest.mark.asyncio
async def test_rejected_command_writes_nothing_to_outbox(test_db):
    """A failed use case leaves no outbox rows behind."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = LoanUnitOfWork(session_factory)
    handler = CreateLoanHandler(
        uow,
        borrower_directory=_borrower_directory(),
        logger=MagicMock(),
    )

    command = CreateLoanCommand(
        reservation_id="33333333-3333-4333-8333-333333333333",
        reservation_generation=1,
        patron_id="patron-outbox-3",
        patron_email="outbox3@example.com",
        catalog_book_id="book-outbox-3",
        book_title="Contended Book",
        borrowed_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
    )
    await handler.handle(command)
    rows_before = await _get_outbox_rows(test_db, LoanCreated)

    # A different reservation for the same book is rejected before commit.
    contending_command = CreateLoanCommand(
        reservation_id="44444444-4444-4444-8444-444444444444",
        reservation_generation=2,
        patron_id="patron-outbox-4",
        patron_email="outbox4@example.com",
        catalog_book_id="book-outbox-3",
        book_title="Contended Book",
        borrowed_at=datetime(2026, 7, 4, 12, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(BookNotAvailableException):
        await handler.handle(contending_command)

    rows_after = await _get_outbox_rows(test_db, LoanCreated)
    assert len(rows_after) == len(rows_before)

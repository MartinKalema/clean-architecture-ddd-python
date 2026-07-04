"""
Integration tests for the transactional outbox.

Verifies that units of work stage domain events into the outbox table in
the same transaction as the aggregate changes.
"""
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.command_handlers.create_loan import (
    CreateLoanCommand,
    CreateLoanHandler,
)
from src.domain.lending import LoanCreated
from src.domain.lending.exceptions import BookNotAvailableException
from src.infrastructure.adapters.events import deserialize_event
from src.infrastructure.adapters.lending import LoanUnitOfWork
from src.infrastructure.adapters.outbox import OutboxMessageModel


async def _get_outbox_rows(test_db, event_type: str) -> list[OutboxMessageModel]:
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            select(OutboxMessageModel).where(OutboxMessageModel.type == event_type)
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_create_loan_writes_loan_created_to_outbox(test_db):
    """Committing a new loan stages a LoanCreated event in the outbox."""
    session_factory = async_sessionmaker(bind=test_db.engine, expire_on_commit=False)
    uow = LoanUnitOfWork(session_factory)
    handler = CreateLoanHandler(uow, logger=MagicMock())

    command = CreateLoanCommand(
        patron_id="patron-outbox-1",
        patron_email="outbox@example.com",
        catalog_book_id="book-outbox-1",
        book_title="The Outbox Pattern",
    )
    result = await handler.handle(command)

    rows = await _get_outbox_rows(test_db, "LoanCreated")
    rows = [r for r in rows if r.aggregateid == result.id]
    assert len(rows) == 1

    row = rows[0]
    assert row.aggregatetype == "loan"
    payload = json.loads(row.payload)
    assert payload["event_type"] == "LoanCreated"
    assert payload["patron_email"] == "outbox@example.com"
    assert payload["book_title"] == "The Outbox Pattern"

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
    handler = CreateLoanHandler(uow, logger=MagicMock())

    command = CreateLoanCommand(
        patron_id="patron-outbox-2",
        patron_email="outbox2@example.com",
        catalog_book_id="book-outbox-2",
        book_title="Event Consumption",
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
    handler = CreateLoanHandler(uow, logger=MagicMock())

    command = CreateLoanCommand(
        patron_id="patron-outbox-3",
        patron_email="outbox3@example.com",
        catalog_book_id="book-outbox-3",
        book_title="Contended Book",
    )
    await handler.handle(command)
    rows_before = await _get_outbox_rows(test_db, "LoanCreated")

    # Same book again: rejected before commit
    with pytest.raises(BookNotAvailableException):
        await handler.handle(command)

    rows_after = await _get_outbox_rows(test_db, "LoanCreated")
    assert len(rows_after) == len(rows_before)

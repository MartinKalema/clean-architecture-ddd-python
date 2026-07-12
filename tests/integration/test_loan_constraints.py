"""Database invariants shared by model metadata and Alembic migrations."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.adapters.lending.loan_model import LoanModel


BORROWED_AT = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


def _loan(
    *,
    loan_id: str,
    reservation_id: str,
    book_id: str,
    status: str,
) -> LoanModel:
    return LoanModel(
        id=loan_id,
        reservation_id=reservation_id,
        reservation_generation=1,
        patron_id=f"patron-{loan_id}",
        patron_email=f"{loan_id}@example.com",
        catalog_book_id=book_id,
        book_title="Constraint Test Book",
        borrowed_at=BORROWED_AT,
        due_date=BORROWED_AT + timedelta(days=14),
        returned_at=BORROWED_AT if status == "returned" else None,
        status=status,
        version=0,
    )


async def _isolated_session(test_db):
    connection = await test_db.engine.connect()
    transaction = await connection.begin()
    return connection, transaction, AsyncSession(
        bind=connection, expire_on_commit=False
    )


@pytest.mark.asyncio
async def test_one_loan_ever_per_reservation(test_db):
    connection, transaction, session = await _isolated_session(test_db)
    try:
        session.add_all(
            [
                _loan(
                    loan_id="reservation-unique-1",
                    reservation_id="11111111-1111-4111-8111-111111111111",
                    book_id="reservation-book-1",
                    status="returned",
                ),
                _loan(
                    loan_id="reservation-unique-2",
                    reservation_id="11111111-1111-4111-8111-111111111111",
                    book_id="reservation-book-2",
                    status="active",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.flush()
    finally:
        await session.rollback()
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest.mark.asyncio
async def test_overdue_and_lost_are_still_outstanding_for_book_uniqueness(test_db):
    for outstanding_status in ("overdue", "lost"):
        connection, transaction, session = await _isolated_session(test_db)
        try:
            session.add_all(
                [
                    _loan(
                        loan_id=f"{outstanding_status}-1",
                        reservation_id=(
                            "22222222-2222-4222-8222-222222222221"
                            if outstanding_status == "overdue"
                            else "22222222-2222-4222-8222-222222222222"
                        ),
                        book_id=f"outstanding-{outstanding_status}",
                        status=outstanding_status,
                    ),
                    _loan(
                        loan_id=f"{outstanding_status}-2",
                        reservation_id=(
                            "33333333-3333-4333-8333-333333333331"
                            if outstanding_status == "overdue"
                            else "33333333-3333-4333-8333-333333333332"
                        ),
                        book_id=f"outstanding-{outstanding_status}",
                        status="active",
                    ),
                ]
            )
            with pytest.raises(IntegrityError):
                await session.flush()
        finally:
            await session.rollback()
            await session.close()
            if transaction.is_active:
                await transaction.rollback()
            await connection.close()


@pytest.mark.asyncio
async def test_terminal_loan_does_not_block_new_outstanding_loan(test_db):
    connection, transaction, session = await _isolated_session(test_db)
    try:
        session.add_all(
            [
                _loan(
                    loan_id="terminal-returned",
                    reservation_id="44444444-4444-4444-8444-444444444441",
                    book_id="terminal-book",
                    status="returned",
                ),
                _loan(
                    loan_id="terminal-cancelled",
                    reservation_id="44444444-4444-4444-8444-444444444442",
                    book_id="terminal-book",
                    status="cancelled",
                ),
                _loan(
                    loan_id="terminal-new-active",
                    reservation_id="44444444-4444-4444-8444-444444444443",
                    book_id="terminal-book",
                    status="active",
                ),
            ]
        )

        await session.flush()
    finally:
        await session.rollback()
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()

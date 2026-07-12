"""Persistence constraints for globally unique Catalog correlations."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.adapters.catalog.book_model import BookModel


def _borrowed_book(
    *, book_id: str, reservation_id: str, current_loan_id: str
) -> BookModel:
    return BookModel(
        id=book_id,
        title=f"Book {book_id}",
        author="Constraint Tester",
        status="borrowed",
        reserved_at=None,
        borrowed_at=datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc),
        return_due_date=datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
        reservation_id=reservation_id,
        reservation_generation=1,
        reserved_patron_id=f"patron-{book_id}",
        reserved_patron_email=f"{book_id}@example.com",
        current_loan_id=current_loan_id,
        version=0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate_field", ["reservation", "current_loan"])
async def test_catalog_correlation_identity_belongs_to_only_one_book(
    test_db, duplicate_field
):
    connection = await test_db.engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        first_reservation = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        first_loan = "catalog-constraint-loan-1"
        session.add_all(
            [
                _borrowed_book(
                    book_id=f"catalog-constraint-{duplicate_field}-1",
                    reservation_id=first_reservation,
                    current_loan_id=first_loan,
                ),
                _borrowed_book(
                    book_id=f"catalog-constraint-{duplicate_field}-2",
                    reservation_id=(
                        first_reservation
                        if duplicate_field == "reservation"
                        else "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
                    ),
                    current_loan_id=(
                        first_loan
                        if duplicate_field == "current_loan"
                        else "catalog-constraint-loan-2"
                    ),
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

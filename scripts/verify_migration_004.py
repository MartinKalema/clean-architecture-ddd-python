#!/usr/bin/env python3
"""Seed and verify a real PostgreSQL upgrade from Alembic 003 to 004."""
import argparse
import asyncio
import os
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


NOW = datetime(2026, 7, 11, 12, 0)


async def seed(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO patrons (
                        id, first_name, last_name, email, membership_tier,
                        is_suspended, registered_at, current_loan_count, version
                    ) VALUES (
                        'legacy-patron', 'Legacy', 'Patron',
                        'authoritative@example.com', 'regular', false,
                        :now, 0, '0'
                    )
                    """
                ),
                {"now": NOW},
            )
            for book_id, status in (
                ("legacy-valid-book", "available"),
                ("legacy-reserved-book", "reserved"),
                ("legacy-returned-book", "borrowed"),
                ("legacy-overdue-book", "available"),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO books (
                            id, title, author, borrowed_at, return_due_date,
                            version, status, reserved_at
                        ) VALUES (
                            :id, :title, 'Migration Tester', :borrowed_at,
                            :due_at, 0, :status, :reserved_at
                        )
                        """
                    ),
                    {
                        "id": book_id,
                        "title": f"Authoritative {book_id}",
                        "borrowed_at": NOW if status == "borrowed" else None,
                        "due_at": (
                            NOW + timedelta(days=14)
                            if status == "borrowed"
                            else None
                        ),
                        "status": status,
                        "reserved_at": (
                            NOW - timedelta(hours=1)
                            if status == "reserved"
                            else None
                        ),
                    },
                )

            loan_rows = (
                (
                    "legacy-valid-loan",
                    "legacy-patron",
                    "spoofed@example.com",
                    "legacy-valid-book",
                    "Spoofed Title",
                    "active",
                    None,
                ),
                (
                    "legacy-reserved-loan",
                    "legacy-patron",
                    "authoritative@example.com",
                    "legacy-reserved-book",
                    "Reserved",
                    "active",
                    None,
                ),
                (
                    "legacy-returned-loan",
                    "legacy-patron",
                    "authoritative@example.com",
                    "legacy-returned-book",
                    "Returned",
                    "returned",
                    NOW,
                ),
                (
                    "legacy-overdue-loan",
                    "legacy-patron",
                    "authoritative@example.com",
                    "legacy-overdue-book",
                    "Overdue",
                    "overdue",
                    None,
                ),
                (
                    "legacy-phantom-loan",
                    "missing-patron",
                    "phantom@example.com",
                    "missing-book",
                    "Phantom",
                    "active",
                    None,
                ),
            )
            for row in loan_rows:
                await connection.execute(
                    text(
                        """
                        INSERT INTO loans (
                            id, patron_id, patron_email, catalog_book_id,
                            book_title, borrowed_at, due_date, returned_at,
                            status, version
                        ) VALUES (
                            :id, :patron_id, :email, :book_id, :title,
                            :borrowed_at, :due_date, :returned_at, :status, '0'
                        )
                        """
                    ),
                    {
                        "id": row[0],
                        "patron_id": row[1],
                        "email": row[2],
                        "book_id": row[3],
                        "title": row[4],
                        "borrowed_at": NOW - timedelta(days=15),
                        "due_date": NOW - timedelta(days=1),
                        "returned_at": row[6],
                        "status": row[5],
                    },
                )
    finally:
        await engine.dispose()


async def verify(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            loans = {
                row["id"]: row
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT id, status, reservation_id,
                                   reservation_generation, patron_id,
                                   patron_email, book_title
                              FROM loans
                             WHERE id LIKE 'legacy-%'
                            """
                        )
                    )
                ).mappings()
            }
            books = {
                row["id"]: row
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT id, status, reservation_id,
                                   reservation_generation, current_loan_id,
                                   last_completed_loan_id, reserved_patron_id
                              FROM books
                             WHERE id LIKE 'legacy-%'
                            """
                        )
                    )
                ).mappings()
            }

            valid_loan = loans["legacy-valid-loan"]
            valid_book = books["legacy-valid-book"]
            assert valid_loan["reservation_id"]
            assert valid_loan["reservation_generation"] == 1
            assert valid_loan["patron_email"] == "authoritative@example.com"
            assert valid_loan["book_title"] == "Authoritative legacy-valid-book"
            assert valid_book["status"] == "borrowed"
            assert valid_book["current_loan_id"] == "legacy-valid-loan"
            assert valid_book["reservation_id"] == valid_loan["reservation_id"]
            assert valid_book["reserved_patron_id"] == "legacy-patron"

            assert loans["legacy-phantom-loan"]["status"] == "cancelled"
            assert loans["legacy-reserved-loan"]["status"] == "cancelled"
            assert books["legacy-reserved-book"]["status"] == "available"
            assert books["legacy-overdue-book"]["status"] == "borrowed"
            assert (
                books["legacy-overdue-book"]["current_loan_id"]
                == "legacy-overdue-loan"
            )
            assert books["legacy-returned-book"]["status"] == "available"
            assert (
                books["legacy-returned-book"]["last_completed_loan_id"]
                == "legacy-returned-loan"
            )
            assert (
                books["legacy-returned-book"]["reservation_id"]
                == loans["legacy-returned-loan"]["reservation_id"]
            )
            assert (
                books["legacy-returned-book"]["reservation_generation"]
                == loans["legacy-returned-loan"]["reservation_generation"]
            )
            assert (
                books["legacy-returned-book"]["reserved_patron_id"]
                == loans["legacy-returned-loan"]["patron_id"]
            )

            indexes = (
                await connection.execute(
                    text(
                        """
                        SELECT indexname, indexdef
                          FROM pg_indexes
                         WHERE tablename IN ('books', 'loans')
                        """
                    )
                )
            ).mappings()
            index_definitions = {
                row["indexname"]: row["indexdef"] for row in indexes
            }
            assert "UNIQUE" in index_definitions[
                "ix_loans_outstanding_book_unique"
            ]
            assert "cancelled" in index_definitions[
                "ix_loans_outstanding_book_unique"
            ]
            assert "UNIQUE" in index_definitions["ix_books_reservation_id"]
            assert "UNIQUE" in index_definitions["ix_books_current_loan_id"]
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("seed", "verify"))
    args = parser.parse_args()
    database_url = os.environ["DATABASE_URL"]
    asyncio.run(seed(database_url) if args.phase == "seed" else verify(database_url))


if __name__ == "__main__":
    main()

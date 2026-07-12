#!/usr/bin/env python3
"""Seed and verify pending polling-outbox transfer through revision 002."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


PENDING_EVENT_ID = "legacy-pending-book-added"
PROCESSED_EVENT_ID = "legacy-processed-book-added"
OCCURRED_AT = datetime(2026, 7, 1, 12, 0)
LEGACY_EVENT_BOOK_ID = "legacy-event-book"
LEGACY_EVENT_LOAN_ID = "legacy-event-loan"
LEGACY_EVENT_PATRON_ID = "legacy-event-patron"
LEGACY_CONTRACT_TYPES = (
    "CatalogBookReserved",
    "CatalogBookBorrowed",
    "CatalogBookReleased",
    "CatalogBookReturned",
    "LoanCreated",
    "LoanCompleted",
)


async def seed(database_url: str) -> None:
    engine = create_async_engine(database_url)
    pending_payload = {
        "event_id": PENDING_EVENT_ID,
        "book_id": "legacy-outbox-book",
        "title": "Legacy Outbox Book",
        "author": "Migration Test",
        "occurred_at": OCCURRED_AT.isoformat(),
    }
    processed_payload = {
        **pending_payload,
        "event_id": PROCESSED_EVENT_ID,
        "book_id": "legacy-processed-book",
    }
    try:
        async with engine.begin() as connection:
            borrowed_at = OCCURRED_AT - timedelta(days=7)
            due_date = OCCURRED_AT + timedelta(days=7)
            await connection.execute(
                text(
                    """
                    INSERT INTO patrons (
                        id, first_name, last_name, email, membership_tier,
                        is_suspended, suspended_reason, registered_at,
                        current_loan_count, version
                    ) VALUES (
                        :patron_id, 'Legacy', 'Event', 'legacy-event@example.com',
                        'regular', false, NULL, :borrowed_at, 1, '0'
                    )
                    """
                ),
                {
                    "patron_id": LEGACY_EVENT_PATRON_ID,
                    "borrowed_at": borrowed_at,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO books (
                        id, title, author, is_borrowed, borrowed_at,
                        return_due_date, version
                    ) VALUES (
                        :book_id, 'Legacy Event Book', 'Migration Test', true,
                        :borrowed_at, :due_date, 0
                    )
                    """
                ),
                {
                    "book_id": LEGACY_EVENT_BOOK_ID,
                    "borrowed_at": borrowed_at,
                    "due_date": due_date,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO loans (
                        id, patron_id, patron_email, catalog_book_id,
                        book_title, borrowed_at, due_date, returned_at,
                        status, version
                    ) VALUES (
                        :loan_id, :patron_id, 'legacy-event@example.com',
                        :book_id, 'Legacy Event Book', :borrowed_at, :due_date,
                        NULL, 'active', '0'
                    )
                    """
                ),
                {
                    "patron_id": LEGACY_EVENT_PATRON_ID,
                    "book_id": LEGACY_EVENT_BOOK_ID,
                    "loan_id": LEGACY_EVENT_LOAN_ID,
                    "borrowed_at": borrowed_at,
                    "due_date": due_date,
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_messages (
                        id, event_type, event_data, created_at, processed_at,
                        is_processed, retry_count, error_message
                    ) VALUES (
                        :pending_id, 'BookAddedToCatalog', :pending_payload,
                        :occurred_at, NULL, false, 2, 'temporary failure'
                    ), (
                        :processed_id, 'BookAddedToCatalog', :processed_payload,
                        :occurred_at, :occurred_at, true, 0, NULL
                    )
                    """
                ),
                {
                    "pending_id": PENDING_EVENT_ID,
                    "processed_id": PROCESSED_EVENT_ID,
                    "pending_payload": json.dumps(pending_payload),
                    "processed_payload": json.dumps(processed_payload),
                    "occurred_at": OCCURRED_AT,
                },
            )

            common = {"occurred_at": OCCURRED_AT.isoformat()}
            event_payloads = {
                "CatalogBookReserved": {
                    **common,
                    "book_id": LEGACY_EVENT_BOOK_ID,
                    "title": "Legacy Event Book",
                    "reserved_at": borrowed_at.isoformat(),
                    "return_due_date": due_date.isoformat(),
                    "borrower_email": "legacy-event@example.com",
                },
                "CatalogBookBorrowed": {
                    **common,
                    "book_id": LEGACY_EVENT_BOOK_ID,
                    "title": "Legacy Event Book",
                    "borrowed_at": borrowed_at.isoformat(),
                    "return_due_date": due_date.isoformat(),
                    "borrower_email": "legacy-event@example.com",
                },
                "CatalogBookReleased": {
                    **common,
                    "book_id": LEGACY_EVENT_BOOK_ID,
                    "reason": "legacy release",
                },
                "CatalogBookReturned": {
                    **common,
                    "book_id": LEGACY_EVENT_BOOK_ID,
                },
                "LoanCreated": {
                    **common,
                    "loan_id": LEGACY_EVENT_LOAN_ID,
                    "patron_id": LEGACY_EVENT_PATRON_ID,
                    "patron_email": "legacy-event@example.com",
                    "book_id": LEGACY_EVENT_BOOK_ID,
                    "book_title": "Legacy Event Book",
                    "borrowed_at": borrowed_at.isoformat(),
                    "due_date": due_date.isoformat(),
                },
                "LoanCompleted": {
                    **common,
                    "loan_id": LEGACY_EVENT_LOAN_ID,
                    "patron_id": LEGACY_EVENT_PATRON_ID,
                    "book_id": LEGACY_EVENT_BOOK_ID,
                    "returned_at": OCCURRED_AT.isoformat(),
                    "was_overdue": False,
                },
            }
            rows = []
            for event_type, payload in event_payloads.items():
                event_id = f"legacy-contract-{event_type.lower()}"
                payload["event_id"] = event_id
                rows.append(
                    {
                        "id": event_id,
                        "event_type": event_type,
                        "event_data": json.dumps(payload),
                        "created_at": OCCURRED_AT,
                    }
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_messages (
                        id, event_type, event_data, created_at, processed_at,
                        is_processed, retry_count, error_message
                    ) VALUES (
                        :id, :event_type, :event_data, :created_at, NULL,
                        false, 1, 'legacy contract pending'
                    )
                    """
                ),
                rows,
            )
    finally:
        await engine.dispose()


async def verify(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            legacy_table_exists = await connection.scalar(
                text("SELECT to_regclass('public.outbox_messages') IS NOT NULL")
            )
            assert legacy_table_exists is False

            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, aggregatetype, aggregateid, type, payload,
                               occurred_at
                          FROM outbox
                         WHERE id IN (:pending_id, :processed_id)
                         ORDER BY id
                        """
                    ),
                    {
                        "pending_id": PENDING_EVENT_ID,
                        "processed_id": PROCESSED_EVENT_ID,
                    },
                )
            ).mappings().all()

            assert len(rows) == 1
            row = rows[0]
            assert row["id"] == PENDING_EVENT_ID
            assert row["aggregatetype"] == "book"
            assert row["aggregateid"] == "legacy-outbox-book"
            assert row["type"] == "BookAddedToCatalog"

            payload = json.loads(row["payload"])
            assert payload["event_id"] == PENDING_EVENT_ID
            assert payload["book_id"] == "legacy-outbox-book"
            assert payload["event_type"] == "BookAddedToCatalog"
            assert payload["occurred_at"] == (
                OCCURRED_AT.replace(tzinfo=timezone.utc).isoformat()
            )
            assert payload["_legacy_delivery"] == {
                "retry_count": 2,
                "last_error": "temporary failure",
                "occurred_at_storage": "utc-naive",
            }

            has_insertion_clock = await connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                          FROM information_schema.columns
                         WHERE table_schema = current_schema()
                           AND table_name = 'outbox'
                           AND column_name = 'inserted_at'
                    )
                    """
                )
            )
            if has_insertion_clock:
                retention_times = (
                    await connection.execute(
                        text(
                            """
                            SELECT occurred_at, inserted_at
                              FROM outbox
                             WHERE id = :event_id
                            """
                        ),
                        {"event_id": PENDING_EVENT_ID},
                    )
                ).mappings().one()
                assert retention_times["inserted_at"] is not None
                assert (
                    retention_times["inserted_at"]
                    > retention_times["occurred_at"]
                )
                assert row["occurred_at"] == OCCURRED_AT.replace(
                    tzinfo=timezone.utc
                )
            else:
                assert row["occurred_at"] == OCCURRED_AT

            audit_table_exists = await connection.scalar(
                text(
                    "SELECT to_regclass('public.legacy_event_migration_audit') "
                    "IS NOT NULL"
                )
            )
            if audit_table_exists:
                from src.infrastructure.adapters.events import deserialize_event

                contract_rows = (
                    await connection.execute(
                        text(
                            """
                            SELECT id, type, payload
                              FROM outbox
                             WHERE id LIKE 'legacy-contract-%'
                                OR (aggregateid = :book_id AND
                                    type = 'library.catalog.book-borrowed.v2')
                             ORDER BY id
                            """
                        ),
                        {"book_id": LEGACY_EVENT_BOOK_ID},
                    )
                ).mappings().all()
                assert len(contract_rows) == len(LEGACY_CONTRACT_TYPES) + 1
                assert all(
                    deserialize_event(json.loads(contract_row["payload"]))
                    is not None
                    for contract_row in contract_rows
                )
                audit_count = await connection.scalar(
                    text(
                        "SELECT count(*) FROM legacy_event_migration_audit "
                        "WHERE event_id LIKE 'legacy-contract-%'"
                    )
                )
                assert audit_count == 3
                loan_status = await connection.scalar(
                    text("SELECT status FROM loans WHERE id = :loan_id"),
                    {"loan_id": LEGACY_EVENT_LOAN_ID},
                )
                book_status = await connection.scalar(
                    text("SELECT status FROM books WHERE id = :book_id"),
                    {"book_id": LEGACY_EVENT_BOOK_ID},
                )
                assert loan_status == "returned"
                assert book_status == "available"
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

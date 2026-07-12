"""Correlate Catalog reservations, Lending loans, and returns.

Every borrow attempt now has a UUID reservation identity and a monotonically
increasing book-local generation (fencing token).  Catalog also records the
exact loan currently holding a book, while Lending enforces both one loan per
reservation and one non-terminal loan per book.

Existing RESERVED rows cannot be correlated safely because the old schema did
not store an owner or token.  They are released, and any tentative outstanding
loan for such a row is cancelled.  Existing outstanding loans for non-reserved
books are treated as the authoritative historical fact and backfilled into
Catalog.  Ambiguous duplicate outstanding loans abort the migration rather
than silently choosing one.

Rows transferred from the polling outbox carry an explicit provenance marker.
This revision enriches LoanCreated/LoanCompleted and exact Catalog returns,
creates the confirmation notification still owed by a pending LoanCreated,
and converts uncorrelatable v1 Catalog messages into a consumable compensation
contract backed by a durable migration-audit row.

Revision ID: 004
Revises: 003
Create Date: 2026-07-11

"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

from migrations.legacy_naive_time import require_legacy_naive_timezone


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LEGACY_RESERVATION_NAMESPACE = uuid.UUID("6303d5a8-7cbc-4ae4-96ea-a907535962f8")
_LEGACY_NOTIFICATION_NAMESPACE = uuid.UUID("6480aa70-37cc-4bc5-b9db-055921c731c1")
_BATCH_SIZE = 1_000
_CORRELATION_V2_EVENTS = {
    "CatalogBookReserved",
    "CatalogBookBorrowed",
    "CatalogBookReleased",
    "CatalogBookReturned",
    "LoanCreated",
    "LoanCompleted",
}


def upgrade() -> None:
    # Old installations may already be stamped 002 even though the historical
    # revision dropped pending polling rows.  Patched 002 creates this table
    # and a proof marker; IF NOT EXISTS lets 004 expose marker absence to the
    # fail-closed check in 005 without pretending the proof exists.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_safety_markers (
            name VARCHAR(128) PRIMARY KEY,
            value VARCHAR(128) NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.create_table(
        "legacy_event_migration_audit",
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "length(event_type) BETWEEN 1 AND 64",
            name="ck_legacy_event_audit_type",
        ),
        sa.CheckConstraint(
            "length(aggregate_type) BETWEEN 1 AND 32",
            name="ck_legacy_event_audit_aggregate_type",
        ),
        sa.CheckConstraint(
            "length(aggregate_id) BETWEEN 1 AND 64",
            name="ck_legacy_event_audit_aggregate_id",
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 1 AND 500",
            name="ck_legacy_event_audit_reason",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )

    op.add_column("books", sa.Column("reservation_id", sa.String(), nullable=True))
    op.add_column(
        "books",
        sa.Column(
            "reservation_generation",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("books", sa.Column("reserved_patron_id", sa.String(), nullable=True))
    op.add_column(
        "books", sa.Column("reserved_patron_email", sa.String(), nullable=True)
    )
    op.add_column("books", sa.Column("current_loan_id", sa.String(), nullable=True))
    op.add_column(
        "books", sa.Column("last_completed_loan_id", sa.String(), nullable=True)
    )

    # Loans are temporarily nullable while deterministic identities are
    # assigned to pre-correlation rows.
    op.add_column("loans", sa.Column("reservation_id", sa.String(), nullable=True))
    op.add_column(
        "loans", sa.Column("reservation_generation", sa.Integer(), nullable=True)
    )
    op.add_column(
        "loans",
        sa.Column(
            "legacy_returned_at_utc",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    connection = op.get_bind()
    _backfill_legacy_loan_reservations(connection)
    _apply_pending_legacy_catalog_returns(connection)

    unknown_statuses = connection.execute(
        sa.text(
            """
            SELECT DISTINCT status
              FROM loans
             WHERE status NOT IN (
                 'active', 'returned', 'overdue', 'lost', 'cancelled'
             )
             ORDER BY status
            """
        )
    ).scalars().all()
    if unknown_statuses:
        raise RuntimeError(
            "Cannot migrate loans with unknown status values: "
            + ", ".join(str(status) for status in unknown_statuses)
        )

    # The removed public loan bypass allowed references and display fields to
    # be supplied by clients.  An outstanding loan with no real aggregate on
    # either side cannot be reconciled, so terminate it as legacy compensation.
    connection.execute(
        sa.text(
            """
            UPDATE loans AS loan
               SET status = 'cancelled'
             WHERE loan.status NOT IN ('returned', 'cancelled')
               AND (
                   NOT EXISTS (
                       SELECT 1 FROM books AS book
                        WHERE book.id = loan.catalog_book_id
                   )
                   OR NOT EXISTS (
                       SELECT 1 FROM patrons AS patron
                        WHERE patron.id = loan.patron_id
                   )
                   OR EXISTS (
                       SELECT 1 FROM books AS book
                        WHERE book.id = loan.catalog_book_id
                          AND (book.title IS NULL OR TRIM(book.title) = '')
                   )
                   OR EXISTS (
                       SELECT 1 FROM patrons AS patron
                        WHERE patron.id = loan.patron_id
                          AND (patron.email IS NULL OR TRIM(patron.email) = '')
                   )
               )
            """
        )
    )

    # For valid outstanding loans, replace client-supplied snapshot text with
    # authoritative aggregate data before it is copied back into Catalog or
    # emitted by any future loan event.
    connection.execute(
        sa.text(
            """
            UPDATE loans AS loan
               SET patron_email = patron.email,
                   book_title = book.title
              FROM patrons AS patron,
                   books AS book
             WHERE loan.status <> 'cancelled'
               AND patron.id = loan.patron_id
               AND book.id = loan.catalog_book_id
            """
        )
    )

    # An old RESERVED row has no trustworthy owner/token.  Its matching loan,
    # if one raced into existence, was never confirmed by Catalog and is a
    # cancellation rather than a completed return.
    connection.execute(
        sa.text(
            """
            UPDATE loans
               SET status = 'cancelled'
             WHERE status NOT IN ('returned', 'cancelled')
               AND catalog_book_id IN (
                   SELECT id FROM books WHERE status = 'reserved'
               )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE books
               SET status = 'available',
                   reserved_at = NULL,
                   borrowed_at = NULL,
                   return_due_date = NULL,
                   reservation_id = NULL,
                   reservation_generation = 0,
                   reserved_patron_id = NULL,
                   reserved_patron_email = NULL,
                   current_loan_id = NULL
             WHERE status = 'reserved'
            """
        )
    )

    duplicates = connection.execute(
        sa.text(
            """
            SELECT catalog_book_id, COUNT(*) AS loan_count
              FROM loans
             WHERE status NOT IN ('returned', 'cancelled')
             GROUP BY catalog_book_id
            HAVING COUNT(*) > 1
             ORDER BY catalog_book_id
             LIMIT 20
            """
        )
    ).mappings().all()
    if duplicates:
        details = ", ".join(
            f"{row['catalog_book_id']} ({row['loan_count']} loans)"
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot establish one outstanding loan per book; reconcile these "
            f"books before retrying migration 004: {details}"
        )

    # Lending is authoritative for an already-created, non-terminal loan.
    # This also repairs historical AVAILABLE+outstanding-loan split states.
    connection.execute(
        sa.text(
            """
            UPDATE books AS book
               SET status = 'borrowed',
                   reserved_at = NULL,
                   borrowed_at = loan.borrowed_at,
                   return_due_date = loan.due_date,
                   reservation_id = loan.reservation_id,
                   reservation_generation = loan.reservation_generation,
                   reserved_patron_id = loan.patron_id,
                   reserved_patron_email = loan.patron_email,
                   current_loan_id = loan.id
              FROM loans AS loan
             WHERE loan.catalog_book_id = book.id
               AND loan.status NOT IN ('returned', 'cancelled')
            """
        )
    )

    # A historical BORROWED row with no outstanding Lending fact cannot be
    # returned safely by identity, so release it instead of preserving a
    # permanently unreturnable catalog lock.
    connection.execute(
        sa.text(
            """
            UPDATE books
               SET status = 'available',
                   borrowed_at = NULL,
                   return_due_date = NULL
             WHERE status = 'borrowed'
               AND current_loan_id IS NULL
            """
        )
    )

    # Preserve idempotence for the most recently completed historical return.
    # PostgreSQL is the supported migration target; ROW_NUMBER keeps the
    # selection deterministic when timestamps tie.
    connection.execute(
        sa.text(
            """
            WITH ranked_returns AS (
                SELECT id,
                       catalog_book_id,
                       reservation_id,
                       reservation_generation,
                       patron_id,
                       patron_email,
                       ROW_NUMBER() OVER (
                           PARTITION BY catalog_book_id
                           ORDER BY returned_at DESC NULLS LAST,
                                    borrowed_at DESC,
                                    id DESC
                       ) AS position
                  FROM loans
                 WHERE status = 'returned'
            )
            UPDATE books AS book
               SET last_completed_loan_id = ranked.id,
                   reservation_id = CASE
                       WHEN book.current_loan_id IS NULL
                       THEN ranked.reservation_id
                       ELSE book.reservation_id
                   END,
                   reservation_generation = CASE
                       WHEN book.current_loan_id IS NULL
                       THEN ranked.reservation_generation
                       ELSE book.reservation_generation
                   END,
                   reserved_patron_id = CASE
                       WHEN book.current_loan_id IS NULL
                       THEN ranked.patron_id
                       ELSE book.reserved_patron_id
                   END,
                   reserved_patron_email = CASE
                       WHEN book.current_loan_id IS NULL
                       THEN ranked.patron_email
                       ELSE book.reserved_patron_email
                   END
              FROM ranked_returns AS ranked
             WHERE ranked.position = 1
               AND ranked.catalog_book_id = book.id
            """
        )
    )

    _upgrade_pending_legacy_events(connection)

    op.alter_column("loans", "reservation_id", nullable=False)
    op.alter_column("loans", "reservation_generation", nullable=False)

    op.create_index(
        "ix_books_reservation_id", "books", ["reservation_id"], unique=True
    )
    op.create_index(
        "ix_books_current_loan_id", "books", ["current_loan_id"], unique=True
    )
    op.create_index(
        "ix_loans_reservation_id_unique",
        "loans",
        ["reservation_id"],
        unique=True,
    )

    op.drop_index("ix_loans_active_book_unique", table_name="loans")
    op.create_index(
        "ix_loans_outstanding_book_unique",
        "loans",
        ["catalog_book_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('returned', 'cancelled')"),
        sqlite_where=sa.text("status NOT IN ('returned', 'cancelled')"),
    )

    op.alter_column("books", "reservation_generation", server_default=None)


def downgrade() -> None:
    raise RuntimeError(
        "Migration 004 is irreversible: removing reservation identity, owner, "
        "generation, and exact loan correlation would make delayed saga "
        "messages unsafe. Restore a pre-004 backup instead."
    )


def _backfill_legacy_loan_reservations(connection: sa.Connection) -> None:
    """Assign stable UUID5 tokens without loading the whole table at once."""
    last_id: str | None = None
    select_batch = sa.text(
        """
        SELECT id
          FROM loans
         WHERE reservation_id IS NULL
           AND (:last_id IS NULL OR id > :last_id)
         ORDER BY id
         LIMIT :batch_size
        """
    ).bindparams(
        sa.bindparam("last_id", type_=sa.String()),
        sa.bindparam("batch_size", type_=sa.Integer()),
    )
    update_row = sa.text(
        """
        UPDATE loans
           SET reservation_id = :reservation_id,
               reservation_generation = 1
         WHERE id = :loan_id
           AND reservation_id IS NULL
        """
    )

    while True:
        rows = connection.execute(
            select_batch,
            {"last_id": last_id, "batch_size": _BATCH_SIZE},
        ).scalars().all()
        if not rows:
            return

        connection.execute(
            update_row,
            [
                {
                    "loan_id": loan_id,
                    "reservation_id": str(
                        uuid.uuid5(
                            _LEGACY_RESERVATION_NAMESPACE,
                            f"legacy-loan:{loan_id}",
                        )
                    ),
                }
                for loan_id in rows
            ],
        )
        last_id = rows[-1]


def _iter_pending_legacy_rows(connection):
    """Yield only rows transferred from the polling outbox by patched 002."""
    last_id: str | None = None
    query = sa.text(
        """
        SELECT id, aggregatetype, aggregateid, type, payload, occurred_at
          FROM outbox
         WHERE payload LIKE '%"_legacy_delivery"%'
           AND (:last_id IS NULL OR id > :last_id)
         ORDER BY id
         LIMIT :batch_size
        """
    ).bindparams(
        sa.bindparam("last_id", type_=sa.String()),
        sa.bindparam("batch_size", type_=sa.Integer()),
    )
    while True:
        rows = connection.execute(
            query,
            {"last_id": last_id, "batch_size": _BATCH_SIZE},
        ).mappings().all()
        if not rows:
            return
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError) as error:
                raise RuntimeError(
                    f"Cannot correlate legacy outbox row {row['id']}: invalid JSON"
                ) from error
            if not isinstance(payload, dict):
                raise RuntimeError(
                    f"Cannot correlate legacy outbox row {row['id']}: "
                    "payload is not an object"
                )
            if (
                "_legacy_delivery" in payload
                and payload.get("event_type") in _CORRELATION_V2_EVENTS
            ):
                yield row, payload
        last_id = rows[-1]["id"]


def _apply_pending_legacy_catalog_returns(connection) -> None:
    """Honor a pending pre-correlation Catalog return in Lending exactly once."""
    legacy_timezone: str | None = None
    for row, payload in _iter_pending_legacy_rows(connection):
        if payload.get("event_type") != "CatalogBookReturned":
            continue
        book_id = payload.get("book_id")
        if not isinstance(book_id, str) or not book_id:
            _compensate_legacy_row(
                connection,
                row,
                payload,
                "legacy Catalog return had no usable book identity",
            )
            continue

        outstanding = connection.execute(
            sa.text(
                """
                SELECT id, reservation_id, reservation_generation, patron_id,
                       borrowed_at, returned_at
                  FROM loans
                 WHERE catalog_book_id = :book_id
                   AND status NOT IN ('returned', 'cancelled')
                 ORDER BY borrowed_at DESC, id DESC
                 LIMIT 2
                """
            ),
            {"book_id": book_id},
        ).mappings().all()
        if len(outstanding) > 1:
            raise RuntimeError(
                f"Cannot correlate legacy Catalog return {row['id']}: "
                f"book {book_id} has multiple outstanding loans"
            )

        if outstanding:
            loan = outstanding[0]
            if legacy_timezone is None:
                legacy_timezone = require_legacy_naive_timezone(
                    has_legacy_timestamps=True,
                    revision=revision,
                )
            returned_at = _legacy_local_naive(
                payload.get("occurred_at"),
                timezone_name=legacy_timezone,
                row_id=row["id"],
            )
            if returned_at < loan["borrowed_at"]:
                _compensate_legacy_row(
                    connection,
                    row,
                    payload,
                    "legacy Catalog return predates the matching loan",
                )
                continue
            connection.execute(
                sa.text(
                    """
                    UPDATE loans
                       SET status = 'returned',
                           returned_at = :returned_at,
                           legacy_returned_at_utc = true
                     WHERE id = :loan_id
                       AND status NOT IN ('returned', 'cancelled')
                    """
                ),
                {
                    "loan_id": loan["id"],
                    "returned_at": _legacy_utc_naive(
                        payload.get("occurred_at"), row_id=row["id"]
                    ),
                },
            )
        else:
            returned = connection.execute(
                sa.text(
                    """
                    SELECT id, reservation_id, reservation_generation,
                           patron_id, borrowed_at, returned_at
                      FROM loans
                     WHERE catalog_book_id = :book_id
                       AND status = 'returned'
                     ORDER BY returned_at DESC NULLS LAST,
                              borrowed_at DESC, id DESC
                     LIMIT 2
                    """
                ),
                {"book_id": book_id},
            ).mappings().all()
            if len(returned) != 1:
                _compensate_legacy_row(
                    connection,
                    row,
                    payload,
                    "legacy Catalog return had no unique Lending loan to reconcile",
                )
                continue
            loan = returned[0]

        payload.update(
            {
                "loan_id": loan["id"],
                "reservation_id": loan["reservation_id"],
                "reservation_generation": loan["reservation_generation"],
                "patron_id": loan["patron_id"],
            }
        )
        _write_legacy_payload(
            connection,
            row_id=row["id"],
            event_type_header="library.catalog.book-returned.v1",
            payload=payload,
        )


def _upgrade_pending_legacy_events(connection) -> None:
    """Make every transferred v1 row consumable or explicitly compensated."""
    compensation_reasons = {
        "CatalogBookReserved": (
            "legacy reservation lacked owner/token fencing and was released "
            "during migration"
        ),
        "CatalogBookBorrowed": (
            "legacy borrowed event lacked exact loan identity; Catalog state "
            "was reconciled from Lending"
        ),
        "CatalogBookReleased": (
            "legacy release lacked exact reservation identity; state was "
            "reconciled during migration"
        ),
    }
    for row, payload in _iter_pending_legacy_rows(connection):
        event_type = payload.get("event_type")
        if event_type in compensation_reasons:
            _compensate_legacy_row(
                connection,
                row,
                payload,
                compensation_reasons[event_type],
            )
            continue
        if event_type == "CatalogBookReturned":
            required = (
                "loan_id",
                "reservation_id",
                "reservation_generation",
                "patron_id",
            )
            if not all(payload.get(name) is not None for name in required):
                _compensate_legacy_row(
                    connection,
                    row,
                    payload,
                    "legacy Catalog return could not be correlated to Lending",
                )
            continue
        if event_type not in {"LoanCreated", "LoanCompleted"}:
            continue

        loan_id = payload.get("loan_id")
        loan = connection.execute(
            sa.text(
                """
                SELECT id, reservation_id, reservation_generation, patron_id,
                       patron_email, catalog_book_id, book_title, borrowed_at,
                       due_date, returned_at, status
                  FROM loans
                 WHERE id = :loan_id
                """
            ),
            {"loan_id": loan_id},
        ).mappings().first()
        if loan is None or (
            event_type == "LoanCreated" and loan["status"] == "cancelled"
        ):
            _compensate_legacy_row(
                connection,
                row,
                payload,
                "legacy loan event had no valid authoritative Lending loan",
            )
            continue

        payload.update(
            {
                "loan_id": loan["id"],
                "reservation_id": loan["reservation_id"],
                "reservation_generation": loan["reservation_generation"],
                "patron_id": loan["patron_id"],
                "book_id": loan["catalog_book_id"],
            }
        )
        if event_type == "LoanCreated":
            payload.update(
                {
                    "patron_email": loan["patron_email"],
                    "book_title": loan["book_title"],
                }
            )
            _write_legacy_payload(
                connection,
                row_id=row["id"],
                event_type_header="library.lending.loan-created.v1",
                payload=payload,
            )
            _insert_legacy_notification_companion(
                connection,
                source_row=row,
                source_payload=payload,
                loan=loan,
            )
        else:
            _write_legacy_payload(
                connection,
                row_id=row["id"],
                event_type_header="library.lending.loan-completed.v1",
                payload=payload,
            )


def _insert_legacy_notification_companion(
    connection,
    *,
    source_row,
    source_payload: dict,
    loan,
) -> None:
    """Preserve the confirmation owed by a pending legacy LoanCreated row."""
    notification_id = str(
        uuid.uuid5(
            _LEGACY_NOTIFICATION_NAMESPACE,
            f"loan-confirmation:{source_row['id']}",
        )
    )
    envelope = {
        "envelope_version": 1,
        "contract": {
            "namespace": "library.catalog",
            "name": "book-borrowed",
            "version": 2,
        },
        "metadata": {
            "event_id": notification_id,
            "occurred_at": source_payload["occurred_at"],
            "correlation_id": notification_id,
            "causation_id": None,
        },
        "data": {
            "book_id": loan["catalog_book_id"],
            "title": loan["book_title"],
            "reservation_id": loan["reservation_id"],
            "reservation_generation": loan["reservation_generation"],
            "patron_id": loan["patron_id"],
            "loan_id": loan["id"],
            "borrowed_at": source_payload["borrowed_at"],
            "return_due_date": source_payload["due_date"],
            "borrower_email": loan["patron_email"],
        },
    }
    connection.execute(
        sa.text(
            """
            INSERT INTO outbox (
                id, aggregatetype, aggregateid, type, payload, occurred_at
            ) VALUES (
                :id, 'book', :book_id, :type, :payload, :occurred_at
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": notification_id,
            "book_id": loan["catalog_book_id"],
            # Revision 005 recognizes this temporary header as exact UTC-naive
            # SQL provenance, converts it without DST reinterpretation, then
            # restores the public v2 header before Debezium starts.
            "type": "library.catalog.book-borrowed.v2.legacy-utc",
            "payload": json.dumps(envelope, separators=(",", ":")),
            "occurred_at": source_row["occurred_at"],
        },
    )


def _compensate_legacy_row(
    connection,
    row,
    payload: dict,
    reason: str,
) -> None:
    reason = " ".join(reason.split())[:500]
    original_event_type = str(payload.get("event_type") or row["type"])
    connection.execute(
        sa.text(
            """
            INSERT INTO legacy_event_migration_audit (
                event_id, event_type, aggregate_type, aggregate_id, reason
            ) VALUES (
                :event_id, :event_type, :aggregate_type, :aggregate_id, :reason
            )
            ON CONFLICT (event_id) DO NOTHING
            """
        ),
        {
            "event_id": row["id"],
            "event_type": original_event_type,
            "aggregate_type": row["aggregatetype"],
            "aggregate_id": row["aggregateid"],
            "reason": reason,
        },
    )
    compensated = {
        "event_type": "LegacyWorkflowCompensated",
        "event_id": payload.get("event_id") or row["id"],
        "occurred_at": payload.get("occurred_at"),
        "correlation_id": payload.get("event_id") or row["id"],
        "causation_id": None,
        "original_event_type": original_event_type,
        "aggregate_type": row["aggregatetype"],
        "aggregate_id": row["aggregateid"],
        "reason": reason,
        "_legacy_delivery": payload.get("_legacy_delivery"),
    }
    _write_legacy_payload(
        connection,
        row_id=row["id"],
        event_type_header="library.migration.workflow-compensated.v1",
        payload=compensated,
    )


def _write_legacy_payload(
    connection,
    *,
    row_id: str,
    event_type_header: str,
    payload: dict,
) -> None:
    connection.execute(
        sa.text(
            """
            UPDATE outbox
               SET type = :event_type, payload = :payload
             WHERE id = :row_id
            """
        ),
        {
            "row_id": row_id,
            "event_type": event_type_header,
            "payload": json.dumps(payload, separators=(",", ":"), default=str),
        },
    )


def _legacy_local_naive(
    value,
    *,
    timezone_name: str,
    row_id: str,
) -> datetime:
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise RuntimeError(
                f"Cannot correlate legacy outbox row {row_id}: invalid occurred_at"
            ) from error
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise RuntimeError(
            f"Cannot correlate legacy outbox row {row_id}: occurred_at "
            "must carry an explicit offset"
        )
    return value.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)


def _legacy_utc_naive(value, *, row_id: str) -> datetime:
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise RuntimeError(
                f"Cannot correlate legacy outbox row {row_id}: invalid occurred_at"
            ) from error
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise RuntimeError(
            f"Cannot correlate legacy outbox row {row_id}: occurred_at "
            "must carry an explicit offset"
        )
    return value.astimezone(timezone.utc).replace(tzinfo=None)

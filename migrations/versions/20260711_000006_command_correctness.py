"""Harden command invariants, UTC timestamps, and durable operation identity.

Revision ID: 006
Revises: 005
Create Date: 2026-07-11
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from migrations.legacy_naive_time import (
    require_legacy_naive_timezone,
    timezone_sql_literal,
    validate_legacy_timestamp_columns,
)


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    duplicate_emails = connection.execute(
        sa.text(
            """
            SELECT lower(trim(email)) AS normalized_email, count(*) AS count
              FROM patrons
             GROUP BY lower(trim(email))
            HAVING count(*) > 1
             ORDER BY normalized_email
             LIMIT 20
            """
        )
    ).mappings().all()
    if duplicate_emails:
        details = ", ".join(
            f"{row['normalized_email']} ({row['count']})" for row in duplicate_emails
        )
        raise RuntimeError(
            "Cannot normalize patron emails with case/whitespace duplicates: "
            + details
        )

    # Canonicalize values before narrowing columns or adding constraints.
    connection.execute(
        sa.text(
            """
            UPDATE books
               SET title = regexp_replace(trim(title), '[[:space:]]+', ' ', 'g'),
                   author = regexp_replace(trim(author), '[[:space:]]+', ' ', 'g'),
                   reserved_patron_email = lower(trim(reserved_patron_email)),
                   borrowed_at = CASE WHEN status = 'reserved' THEN NULL ELSE borrowed_at END,
                   return_due_date = CASE WHEN status = 'reserved' THEN NULL ELSE return_due_date END
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE patrons
               SET first_name = regexp_replace(trim(first_name), '[[:space:]]+', ' ', 'g'),
                   last_name = regexp_replace(trim(last_name), '[[:space:]]+', ' ', 'g'),
                   email = lower(trim(email)),
                   membership_tier = COALESCE(membership_tier, 'regular'),
                   is_suspended = COALESCE(is_suspended, false),
                   suspended_reason = CASE
                       WHEN COALESCE(is_suspended, false)
                       THEN regexp_replace(trim(suspended_reason), '[[:space:]]+', ' ', 'g')
                       ELSE NULL
                   END
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE loans
               SET patron_email = lower(trim(patron_email)),
                   book_title = regexp_replace(trim(book_title), '[[:space:]]+', ' ', 'g'),
                   status = CASE
                       WHEN returned_at IS NOT NULL AND status <> 'returned'
                       THEN 'returned'
                       ELSE status
                   END
            """
        )
    )

    # Migration 004 treated legacy status as the terminality signal. Some
    # legacy rows instead carried returned_at while still saying active,
    # overdue, or lost. After the loan normalization above, reconcile Catalog
    # by the exact identity 004 recorded; otherwise head would preserve a
    # BORROWED book backed by a terminal loan.
    connection.execute(
        sa.text(
            """
            UPDATE books AS book
               SET status = 'available',
                   reserved_at = NULL,
                   borrowed_at = NULL,
                   return_due_date = NULL,
                   current_loan_id = NULL,
                   last_completed_loan_id = loan.id,
                   reservation_id = loan.reservation_id,
                   reservation_generation = loan.reservation_generation,
                   reserved_patron_id = loan.patron_id,
                   reserved_patron_email = loan.patron_email
              FROM loans AS loan
             WHERE loan.status = 'returned'
               AND book.current_loan_id = loan.id
            """
        )
    )

    invalid_counts = connection.execute(
        sa.text(
            """
            SELECT
                count(*) FILTER (
                    WHERE length(id) NOT BETWEEN 1 AND 64
                       OR id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                       OR title IS NULL OR length(title) NOT BETWEEN 1 AND 100
                       OR author IS NULL OR length(author) NOT BETWEEN 1 AND 200
                       OR status NOT IN ('available', 'reserved', 'borrowed')
                       OR reservation_generation < 0
                       OR (reservation_id IS NOT NULL AND (
                           length(reservation_id) <> 36 OR
                           reservation_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                       ))
                       OR (reserved_patron_id IS NOT NULL AND (
                           length(reserved_patron_id) NOT BETWEEN 1 AND 64 OR
                           reserved_patron_id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                       ))
                       OR (reserved_patron_email IS NOT NULL AND (
                           length(reserved_patron_email) NOT BETWEEN 3 AND 254 OR
                           reserved_patron_email !~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'
                       ))
                       OR (current_loan_id IS NOT NULL AND (
                           length(current_loan_id) NOT BETWEEN 1 AND 64 OR
                           current_loan_id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                       ))
                       OR (last_completed_loan_id IS NOT NULL AND (
                           length(last_completed_loan_id) NOT BETWEEN 1 AND 64 OR
                           last_completed_loan_id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                       ))
                ) AS invalid_books,
                (SELECT count(*) FROM patrons
                  WHERE length(id) NOT BETWEEN 1 AND 64
                     OR id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                     OR length(first_name) NOT BETWEEN 1 AND 100
                     OR length(last_name) NOT BETWEEN 1 AND 100
                     OR length(email) NOT BETWEEN 3 AND 254
                     OR email !~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'
                     OR membership_tier NOT IN ('regular', 'premium', 'researcher')
                     OR version !~ '^[0-9]+$'
                     OR (is_suspended AND (
                         suspended_reason IS NULL OR
                         length(suspended_reason) NOT BETWEEN 1 AND 500
                     ))) AS invalid_patrons,
                (SELECT count(*) FROM loans
                  WHERE length(id) NOT BETWEEN 1 AND 64
                     OR id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                     OR length(patron_id) NOT BETWEEN 1 AND 64
                     OR patron_id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                     OR length(catalog_book_id) NOT BETWEEN 1 AND 64
                     OR catalog_book_id !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'
                     OR length(reservation_id) <> 36
                     OR reservation_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                     OR reservation_generation < 1
                     OR due_date <= borrowed_at
                     OR (returned_at IS NOT NULL AND NOT legacy_returned_at_utc
                         AND returned_at < borrowed_at)
                     OR length(book_title) NOT BETWEEN 1 AND 100
                     OR length(patron_email) NOT BETWEEN 3 AND 254
                     OR patron_email !~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'
                     OR status NOT IN ('active', 'returned', 'overdue', 'lost', 'cancelled')
                     OR ((status = 'returned') <> (returned_at IS NOT NULL))
                     OR version !~ '^[0-9]+$')
                    AS invalid_loans
              FROM books
            """
        )
    ).mappings().one()
    if any(invalid_counts.values()):
        raise RuntimeError(
            "Migration 006 found irreparable invalid legacy rows: "
            f"books={invalid_counts['invalid_books']}, "
            f"patrons={invalid_counts['invalid_patrons']}, "
            f"loans={invalid_counts['invalid_loans']}"
        )

    # Legacy AVAILABLE rows must not retain transient lifecycle timestamps.
    connection.execute(
        sa.text(
            """
            UPDATE books
               SET reserved_at = NULL,
                   borrowed_at = NULL,
                   return_due_date = NULL,
                   current_loan_id = NULL
             WHERE status = 'available'
            """
        )
    )

    _timestamps_to_utc(connection)
    op.drop_column("loans", "legacy_returned_at_utc")

    op.alter_column("loans", "version", type_=sa.Integer(), postgresql_using="version::integer")
    op.alter_column("patrons", "version", type_=sa.Integer(), postgresql_using="version::integer")

    op.alter_column("books", "title", type_=sa.String(100), nullable=False)
    op.alter_column("books", "id", type_=sa.String(64), nullable=False)
    op.alter_column("books", "author", type_=sa.String(200), nullable=False)
    op.alter_column("books", "status", type_=sa.String(16), nullable=False)
    op.alter_column("books", "reservation_id", type_=sa.String(36))
    op.alter_column("books", "reserved_patron_id", type_=sa.String(64))
    op.alter_column("books", "reserved_patron_email", type_=sa.String(254))
    op.alter_column("books", "current_loan_id", type_=sa.String(64))
    op.alter_column("books", "last_completed_loan_id", type_=sa.String(64))

    op.alter_column("loans", "id", type_=sa.String(64), nullable=False)
    op.alter_column("loans", "patron_id", type_=sa.String(64), nullable=False)
    op.alter_column("loans", "patron_email", type_=sa.String(254), nullable=False)
    op.alter_column("loans", "catalog_book_id", type_=sa.String(64), nullable=False)
    op.alter_column("loans", "book_title", type_=sa.String(100), nullable=False)
    op.alter_column("loans", "reservation_id", type_=sa.String(36), nullable=False)
    op.alter_column("loans", "status", type_=sa.String(16), nullable=False)

    op.alter_column("patrons", "id", type_=sa.String(64), nullable=False)
    op.alter_column("patrons", "first_name", type_=sa.String(100), nullable=False)
    op.alter_column("patrons", "last_name", type_=sa.String(100), nullable=False)
    op.alter_column("patrons", "email", type_=sa.String(254), nullable=False)
    op.alter_column("patrons", "membership_tier", type_=sa.String(16), nullable=False)
    op.alter_column("patrons", "is_suspended", nullable=False)
    op.alter_column("patrons", "suspended_reason", type_=sa.String(500))

    op.drop_column("patrons", "current_loan_count")

    _create_checks()
    _create_application_state_tables()
    _backfill_borrow_operations(connection)


def downgrade() -> None:
    raise RuntimeError(
        "Migration 006 is irreversible: removing command receipts, operation "
        "state, UTC timestamps, and database invariants would re-enable "
        "duplicate commands and invalid aggregates. Restore a pre-006 backup "
        "instead."
    )


def _create_checks() -> None:
    op.create_check_constraint(
        "ck_books_status", "books", "status IN ('available', 'reserved', 'borrowed')"
    )
    op.create_check_constraint(
        "ck_books_reservation_generation", "books", "reservation_generation >= 0"
    )
    op.create_check_constraint(
        "ck_books_id", "books", "id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'"
    )
    op.create_check_constraint(
        "ck_books_reservation_id",
        "books",
        "reservation_id IS NULL OR reservation_id ~* "
        "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
    )
    op.create_check_constraint(
        "ck_books_reserved_patron_id",
        "books",
        "reserved_patron_id IS NULL OR reserved_patron_id ~ "
        "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
    )
    op.create_check_constraint(
        "ck_books_current_loan_id",
        "books",
        "current_loan_id IS NULL OR current_loan_id ~ "
        "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
    )
    op.create_check_constraint(
        "ck_books_last_completed_loan_id",
        "books",
        "last_completed_loan_id IS NULL OR last_completed_loan_id ~ "
        "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
    )
    op.create_check_constraint("ck_books_version", "books", "version >= 0")
    op.create_check_constraint(
        "ck_books_title", "books", "length(trim(title)) BETWEEN 1 AND 100"
    )
    op.create_check_constraint(
        "ck_books_author", "books", "length(trim(author)) BETWEEN 1 AND 200"
    )
    op.create_check_constraint(
        "ck_books_reserved_patron_email",
        "books",
        "reserved_patron_email IS NULL OR ("
        "reserved_patron_email = lower(trim(reserved_patron_email)) AND "
        "length(reserved_patron_email) BETWEEN 3 AND 254 AND "
        "reserved_patron_email ~ "
        "'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$')",
    )
    op.create_check_constraint(
        "ck_books_reserved_state",
        "books",
        "status <> 'reserved' OR (reservation_generation >= 1 AND "
        "reservation_id IS NOT NULL AND "
        "reserved_at IS NOT NULL AND reserved_patron_id IS NOT NULL AND "
        "reserved_patron_email IS NOT NULL AND current_loan_id IS NULL AND "
        "borrowed_at IS NULL AND return_due_date IS NULL)",
    )
    op.create_check_constraint(
        "ck_books_borrowed_state",
        "books",
        "status <> 'borrowed' OR (reservation_generation >= 1 AND "
        "reservation_id IS NOT NULL AND reserved_at IS NULL "
        "AND reserved_patron_id IS NOT NULL AND reserved_patron_email IS NOT NULL "
        "AND current_loan_id IS NOT NULL AND borrowed_at IS NOT NULL "
        "AND return_due_date > borrowed_at)",
    )
    op.create_check_constraint(
        "ck_books_available_state",
        "books",
        "status <> 'available' OR (current_loan_id IS NULL AND reserved_at IS NULL "
        "AND borrowed_at IS NULL AND return_due_date IS NULL)",
    )

    op.create_check_constraint(
        "ck_loans_status",
        "loans",
        "status IN ('active', 'returned', 'overdue', 'lost', 'cancelled')",
    )
    op.create_check_constraint(
        "ck_loans_reservation_generation", "loans", "reservation_generation >= 1"
    )
    op.create_check_constraint(
        "ck_loans_id", "loans", "id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'"
    )
    op.create_check_constraint(
        "ck_loans_patron_id",
        "loans",
        "patron_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
    )
    op.create_check_constraint(
        "ck_loans_catalog_book_id",
        "loans",
        "catalog_book_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
    )
    op.create_check_constraint(
        "ck_loans_reservation_id",
        "loans",
        "reservation_id ~* "
        "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
    )
    op.create_check_constraint("ck_loans_version", "loans", "version >= 0")
    op.create_check_constraint("ck_loans_due_after_borrow", "loans", "due_date > borrowed_at")
    op.create_check_constraint(
        "ck_loans_return_after_borrow",
        "loans",
        "returned_at IS NULL OR returned_at >= borrowed_at",
    )
    op.create_check_constraint(
        "ck_loans_returned_state",
        "loans",
        "(status = 'returned' AND returned_at IS NOT NULL) OR "
        "(status <> 'returned' AND returned_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_loans_patron_email",
        "loans",
        "patron_email = lower(trim(patron_email)) AND "
        "length(patron_email) BETWEEN 3 AND 254 AND "
        "patron_email ~ "
        "'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'",
    )
    op.create_check_constraint(
        "ck_loans_book_title", "loans", "length(trim(book_title)) BETWEEN 1 AND 100"
    )

    op.create_check_constraint(
        "ck_patrons_membership_tier",
        "patrons",
        "membership_tier IN ('regular', 'premium', 'researcher')",
    )
    op.create_check_constraint(
        "ck_patrons_id", "patrons", "id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'"
    )
    op.create_check_constraint("ck_patrons_version", "patrons", "version >= 0")
    op.create_check_constraint(
        "ck_patrons_first_name", "patrons", "length(trim(first_name)) BETWEEN 1 AND 100"
    )
    op.create_check_constraint(
        "ck_patrons_last_name", "patrons", "length(trim(last_name)) BETWEEN 1 AND 100"
    )
    op.create_check_constraint(
        "ck_patrons_email_normalized", "patrons", "email = lower(trim(email))"
    )
    op.create_check_constraint(
        "ck_patrons_email_length", "patrons", "length(email) BETWEEN 3 AND 254"
    )
    op.create_check_constraint(
        "ck_patrons_email_format",
        "patrons",
        "email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'",
    )
    op.create_check_constraint(
        "ck_patrons_suspension_state",
        "patrons",
        "(is_suspended AND suspended_reason IS NOT NULL AND "
        "length(trim(suspended_reason)) BETWEEN 1 AND 500) "
        "OR (NOT is_suspended AND suspended_reason IS NULL)",
    )


def _create_application_state_tables() -> None:
    op.create_table(
        "command_receipts",
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("scope", "idempotency_key", name="pk_command_receipts"),
        sa.CheckConstraint("length(scope) BETWEEN 1 AND 64", name="ck_command_receipts_scope"),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128 AND "
            "idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_command_receipts_key",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_command_receipts_hash",
        ),
    )
    op.create_index(
        "ix_command_receipts_created_at", "command_receipts", ["created_at"]
    )

    op.create_table(
        "borrow_operations",
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("patron_id", sa.String(64), nullable=False),
        sa.Column("reservation_generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("loan_id", sa.String(64), nullable=True),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.CheckConstraint(
            "status IN ('reserved', 'borrowed', 'released', 'returned')",
            name="ck_borrow_operations_status",
        ),
        sa.CheckConstraint(
            "reservation_generation >= 1", name="ck_borrow_operations_generation"
        ),
        sa.CheckConstraint(
            "updated_at >= created_at", name="ck_borrow_operations_timestamps"
        ),
        sa.CheckConstraint(
            "operation_id ~* "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_borrow_operations_id",
        ),
        sa.CheckConstraint(
            "book_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_borrow_operations_book_id",
        ),
        sa.CheckConstraint(
            "patron_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_borrow_operations_patron_id",
        ),
        sa.CheckConstraint(
            "loan_id IS NULL OR loan_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_borrow_operations_loan_id",
        ),
        sa.CheckConstraint(
            "(status = 'reserved' AND loan_id IS NULL AND failure_reason IS NULL) OR "
            "(status = 'borrowed' AND loan_id IS NOT NULL AND failure_reason IS NULL) OR "
            "(status = 'returned' AND loan_id IS NOT NULL AND failure_reason IS NULL) OR "
            "(status = 'released' AND loan_id IS NULL AND "
            "failure_reason IS NOT NULL AND "
            "length(trim(failure_reason)) BETWEEN 1 AND 500)",
            name="ck_borrow_operations_state",
        ),
    )
    op.create_index("ix_borrow_operations_book_id", "borrow_operations", ["book_id"])
    op.create_index(
        "ix_borrow_operations_status_updated",
        "borrow_operations",
        ["status", "updated_at"],
    )


def _backfill_borrow_operations(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO borrow_operations (
                operation_id, book_id, patron_id, reservation_generation,
                status, loan_id, failure_reason, created_at, updated_at
            )
            SELECT reservation_id,
                   id,
                   reserved_patron_id,
                   reservation_generation,
                   CASE
                       WHEN status = 'reserved' THEN 'reserved'
                       WHEN status = 'borrowed' THEN 'borrowed'
                       WHEN last_completed_loan_id IS NOT NULL THEN 'returned'
                       ELSE 'released'
                   END,
                   CASE
                       WHEN status = 'borrowed' THEN current_loan_id
                       WHEN last_completed_loan_id IS NOT NULL THEN last_completed_loan_id
                       ELSE NULL
                   END,
                   CASE
                       WHEN status = 'available' AND last_completed_loan_id IS NULL
                       THEN 'released before durable operation tracking'
                       ELSE NULL
                   END,
                   COALESCE(reserved_at, borrowed_at, CURRENT_TIMESTAMP),
                   CURRENT_TIMESTAMP
              FROM books
             WHERE reservation_id IS NOT NULL
               AND reserved_patron_id IS NOT NULL
               AND reservation_generation >= 1
            ON CONFLICT (operation_id) DO NOTHING
            """
        )
    )


def _timestamps_to_utc(connection: sa.Connection) -> None:
    has_legacy_timestamps = bool(
        connection.scalar(
            sa.text(
                """
                SELECT EXISTS (
                    SELECT 1
                      FROM books
                     WHERE reserved_at IS NOT NULL
                        OR borrowed_at IS NOT NULL
                        OR return_due_date IS NOT NULL
                    UNION ALL
                    SELECT 1
                      FROM loans
                     WHERE borrowed_at IS NOT NULL
                        OR due_date IS NOT NULL
                        OR returned_at IS NOT NULL
                    UNION ALL
                    SELECT 1
                      FROM patrons
                     WHERE registered_at IS NOT NULL
                )
                """
            )
        )
    )
    legacy_timezone = require_legacy_naive_timezone(
        has_legacy_timestamps=has_legacy_timestamps,
        revision=revision,
    )
    timestamp_columns = {
        "books": ("reserved_at", "borrowed_at", "return_due_date"),
        "loans": ("borrowed_at", "due_date", "returned_at"),
        "patrons": ("registered_at",),
    }
    validate_legacy_timestamp_columns(
        connection,
        table_columns=timestamp_columns,
        timezone_name=legacy_timezone,
        revision=revision,
        trusted_utc_flags={
            ("loans", "returned_at"): "legacy_returned_at_utc",
        },
    )
    legacy_timezone_literal = timezone_sql_literal(legacy_timezone)
    for table, columns in timestamp_columns.items():
        for column in columns:
            using_expression = (
                f"CASE WHEN legacy_returned_at_utc "
                f"THEN {column} AT TIME ZONE 'UTC' ELSE "
                f"{column} AT TIME ZONE {legacy_timezone_literal} END"
                if table == "loans" and column == "returned_at"
                else f"{column} AT TIME ZONE {legacy_timezone_literal}"
            )
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=True),
                postgresql_using=using_expression,
            )

"""Create the current pre-release schema.

Revision ID: baseline_20260712
Revises:
Create Date: 2026-07-12

The application has not been released, so this is the only supported database
starting point. It intentionally contains no upgrade or data-conversion path
for earlier development schemas.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "baseline_20260712"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("The application schema requires PostgreSQL")
    has_pg_trgm = bind.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")
    )
    if has_pg_trgm is not True:
        raise RuntimeError(
            "The pg_trgm extension must be provisioned before migrations run"
        )

    _create_books()
    _create_loans()
    _create_patrons()
    _create_outbox()
    _create_command_receipts()
    _create_borrow_operations()
    _create_event_inbox()
    _create_event_quarantine()


def _create_books() -> None:
    op.create_table(
        "books",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("author", sa.String(200), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="available",
        ),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("borrowed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("return_due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reservation_id", sa.String(36), nullable=True),
        sa.Column("reservation_generation", sa.Integer(), nullable=False),
        sa.Column("reserved_patron_id", sa.String(64), nullable=True),
        sa.Column("reserved_patron_email", sa.String(254), nullable=True),
        sa.Column("current_loan_id", sa.String(64), nullable=True),
        sa.Column("last_completed_loan_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('available', 'reserved', 'borrowed')",
            name="ck_books_status",
        ),
        sa.CheckConstraint(
            "reservation_generation >= 0",
            name="ck_books_reservation_generation",
        ),
        sa.CheckConstraint(
            "id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_books_id",
        ),
        sa.CheckConstraint(
            "reservation_id IS NULL OR reservation_id ~* "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_books_reservation_id",
        ),
        sa.CheckConstraint(
            "reserved_patron_id IS NULL OR reserved_patron_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_books_reserved_patron_id",
        ),
        sa.CheckConstraint(
            "current_loan_id IS NULL OR current_loan_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_books_current_loan_id",
        ),
        sa.CheckConstraint(
            "last_completed_loan_id IS NULL OR last_completed_loan_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_books_last_completed_loan_id",
        ),
        sa.CheckConstraint("version >= 0", name="ck_books_version"),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 100", name="ck_books_title"
        ),
        sa.CheckConstraint(
            "length(trim(author)) BETWEEN 1 AND 200", name="ck_books_author"
        ),
        sa.CheckConstraint(
            "reserved_patron_email IS NULL OR ("
            "reserved_patron_email = lower(trim(reserved_patron_email)) AND "
            "length(reserved_patron_email) BETWEEN 3 AND 254 AND "
            "reserved_patron_email ~ "
            "'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$')",
            name="ck_books_reserved_patron_email",
        ),
        sa.CheckConstraint(
            "status <> 'reserved' OR (reservation_generation >= 1 AND "
            "reservation_id IS NOT NULL AND reserved_at IS NOT NULL AND "
            "reserved_patron_id IS NOT NULL AND reserved_patron_email IS NOT NULL AND "
            "current_loan_id IS NULL AND borrowed_at IS NULL AND "
            "return_due_date IS NULL)",
            name="ck_books_reserved_state",
        ),
        sa.CheckConstraint(
            "status <> 'borrowed' OR (reservation_generation >= 1 AND "
            "reservation_id IS NOT NULL AND reserved_at IS NULL AND "
            "reserved_patron_id IS NOT NULL AND reserved_patron_email IS NOT NULL AND "
            "current_loan_id IS NOT NULL AND borrowed_at IS NOT NULL AND "
            "return_due_date > borrowed_at)",
            name="ck_books_borrowed_state",
        ),
        sa.CheckConstraint(
            "status <> 'available' OR (current_loan_id IS NULL AND "
            "reserved_at IS NULL AND borrowed_at IS NULL AND "
            "return_due_date IS NULL)",
            name="ck_books_available_state",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_books_status", "books", ["status"])
    op.create_index("ix_books_reservation_id", "books", ["reservation_id"], unique=True)
    op.create_index("ix_books_current_loan_id", "books", ["current_loan_id"], unique=True)
    op.create_index("ix_books_status_reserved_at", "books", ["status", "reserved_at"])
    op.create_index(
        "ix_books_title_trgm",
        "books",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_books_author_trgm",
        "books",
        ["author"],
        postgresql_using="gin",
        postgresql_ops={"author": "gin_trgm_ops"},
    )
    op.execute("CREATE INDEX ix_books_title_lower_id ON books (lower(title), id)")


def _create_loans() -> None:
    op.create_table(
        "loans",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("patron_id", sa.String(64), nullable=False),
        sa.Column("patron_email", sa.String(254), nullable=False),
        sa.Column("catalog_book_id", sa.String(64), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=False),
        sa.Column("reservation_generation", sa.Integer(), nullable=False),
        sa.Column("book_title", sa.String(100), nullable=False),
        sa.Column("borrowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'returned', 'overdue', 'lost', 'cancelled')",
            name="ck_loans_status",
        ),
        sa.CheckConstraint(
            "reservation_generation >= 1",
            name="ck_loans_reservation_generation",
        ),
        sa.CheckConstraint("id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'", name="ck_loans_id"),
        sa.CheckConstraint(
            "patron_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_loans_patron_id",
        ),
        sa.CheckConstraint(
            "catalog_book_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_loans_catalog_book_id",
        ),
        sa.CheckConstraint(
            "reservation_id ~* "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_loans_reservation_id",
        ),
        sa.CheckConstraint("version >= 0", name="ck_loans_version"),
        sa.CheckConstraint("due_date > borrowed_at", name="ck_loans_due_after_borrow"),
        sa.CheckConstraint(
            "returned_at IS NULL OR returned_at >= borrowed_at",
            name="ck_loans_return_after_borrow",
        ),
        sa.CheckConstraint(
            "(status = 'returned' AND returned_at IS NOT NULL) OR "
            "(status <> 'returned' AND returned_at IS NULL)",
            name="ck_loans_returned_state",
        ),
        sa.CheckConstraint(
            "patron_email = lower(trim(patron_email)) AND "
            "length(patron_email) BETWEEN 3 AND 254 AND patron_email ~ "
            "'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'",
            name="ck_loans_patron_email",
        ),
        sa.CheckConstraint(
            "length(trim(book_title)) BETWEEN 1 AND 100",
            name="ck_loans_book_title",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_loans_patron_id", "loans", ["patron_id"])
    op.create_index("ix_loans_catalog_book_id", "loans", ["catalog_book_id"])
    op.create_index("ix_loans_borrowed_at", "loans", ["borrowed_at"])
    op.create_index("ix_loans_due_date", "loans", ["due_date"])
    op.create_index("ix_loans_status", "loans", ["status"])
    op.create_index("ix_loans_patron_id_status", "loans", ["patron_id", "status"])
    op.create_index(
        "ix_loans_catalog_book_id_status",
        "loans",
        ["catalog_book_id", "status"],
    )
    op.create_index(
        "ix_loans_reservation_id_unique",
        "loans",
        ["reservation_id"],
        unique=True,
    )
    op.create_index(
        "ix_loans_outstanding_book_unique",
        "loans",
        ["catalog_book_id"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('returned', 'cancelled')"),
    )
    op.execute(
        "CREATE INDEX ix_loans_patron_borrowed_id "
        "ON loans (patron_id, borrowed_at DESC, id)"
    )
    op.create_index(
        "ix_loans_outstanding_due_date_id",
        "loans",
        ["due_date", "id"],
        postgresql_where=sa.text("status NOT IN ('returned', 'cancelled')"),
    )


def _create_patrons() -> None:
    op.create_table(
        "patrons",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("membership_tier", sa.String(16), nullable=False),
        sa.Column("is_suspended", sa.Boolean(), nullable=False),
        sa.Column("suspended_reason", sa.String(500), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "membership_tier IN ('regular', 'premium', 'researcher')",
            name="ck_patrons_membership_tier",
        ),
        sa.CheckConstraint("id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'", name="ck_patrons_id"),
        sa.CheckConstraint("version >= 0", name="ck_patrons_version"),
        sa.CheckConstraint(
            "length(trim(first_name)) BETWEEN 1 AND 100",
            name="ck_patrons_first_name",
        ),
        sa.CheckConstraint(
            "length(trim(last_name)) BETWEEN 1 AND 100",
            name="ck_patrons_last_name",
        ),
        sa.CheckConstraint(
            "email = lower(trim(email))", name="ck_patrons_email_normalized"
        ),
        sa.CheckConstraint(
            "length(email) BETWEEN 3 AND 254", name="ck_patrons_email_length"
        ),
        sa.CheckConstraint(
            "email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'",
            name="ck_patrons_email_format",
        ),
        sa.CheckConstraint(
            "(is_suspended AND suspended_reason IS NOT NULL AND "
            "length(trim(suspended_reason)) BETWEEN 1 AND 500) OR "
            "(NOT is_suspended AND suspended_reason IS NULL)",
            name="ck_patrons_suspension_state",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patrons_email", "patrons", ["email"], unique=True)
    op.create_index("ix_patrons_is_suspended", "patrons", ["is_suspended"])
    op.create_index("ix_patrons_membership_tier", "patrons", ["membership_tier"])
    op.create_index("ix_patrons_registered_at_id", "patrons", ["registered_at", "id"])


def _create_outbox() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("aggregatetype", sa.String(32), nullable=False),
        sa.Column("aggregateid", sa.String(64), nullable=False),
        sa.Column("type", sa.String(160), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'", name="ck_outbox_event_id"
        ),
        sa.CheckConstraint(
            "aggregatetype ~ '^[a-z][a-z0-9_-]{0,31}$'",
            name="ck_outbox_aggregate_type",
        ),
        sa.CheckConstraint(
            "aggregateid ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_outbox_aggregate_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_inserted_at_id", "outbox", ["inserted_at", "id"])


def _create_command_receipts() -> None:
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
        sa.CheckConstraint(
            "length(scope) BETWEEN 1 AND 64", name="ck_command_receipts_scope"
        ),
        sa.CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128 AND "
            "idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_command_receipts_key",
        ),
        sa.CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'", name="ck_command_receipts_hash"
        ),
        sa.PrimaryKeyConstraint("scope", "idempotency_key"),
    )
    op.create_index(
        "ix_command_receipts_created_at", "command_receipts", ["created_at"]
    )


def _create_borrow_operations() -> None:
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
            "(status = 'released' AND loan_id IS NULL AND failure_reason IS NOT NULL "
            "AND length(trim(failure_reason)) BETWEEN 1 AND 500)",
            name="ck_borrow_operations_state",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index("ix_borrow_operations_book_id", "borrow_operations", ["book_id"])
    op.create_index(
        "ix_borrow_operations_status_updated",
        "borrow_operations",
        ["status", "updated_at"],
    )


def _create_event_inbox() -> None:
    op.create_table(
        "event_inbox",
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("handler_name", sa.String(128), nullable=False),
        sa.Column("contract_name", sa.String(160), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("causation_id", sa.String(128), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("claim_token", sa.String(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('processing', 'processed', 'failed')",
            name="ck_event_inbox_status",
        ),
        sa.CheckConstraint("attempts >= 1", name="ck_event_inbox_attempts"),
        sa.CheckConstraint(
            "contract_version >= 1", name="ck_event_inbox_contract_version"
        ),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_event_inbox_payload_hash",
        ),
        sa.CheckConstraint(
            "event_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_event_id",
        ),
        sa.CheckConstraint(
            "handler_name ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_handler_name",
        ),
        sa.CheckConstraint(
            "contract_name ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_contract_name",
        ),
        sa.CheckConstraint(
            "correlation_id IS NULL OR correlation_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_correlation_id",
        ),
        sa.CheckConstraint(
            "causation_id IS NULL OR causation_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_causation_id",
        ),
        sa.CheckConstraint(
            "(status = 'processing' AND claim_token IS NOT NULL AND "
            "lease_until IS NOT NULL AND processed_at IS NULL) OR "
            "(status = 'processed' AND claim_token IS NULL AND "
            "lease_until IS NULL AND processed_at IS NOT NULL) OR "
            "(status = 'failed' AND claim_token IS NULL AND "
            "lease_until IS NULL AND processed_at IS NULL)",
            name="ck_event_inbox_status_fields",
        ),
        sa.PrimaryKeyConstraint("event_id", "handler_name"),
    )
    op.create_index("ix_event_inbox_status_lease", "event_inbox", ["status", "lease_until"])
    op.create_index("ix_event_inbox_processed_at", "event_inbox", ["processed_at"])


def _create_event_quarantine() -> None:
    op.create_table(
        "event_quarantine",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=True),
        sa.Column("topic", sa.String(249), nullable=False),
        sa.Column("message_key", sa.Text(), nullable=True),
        sa.Column("contract_name", sa.String(160), nullable=True),
        sa.Column("contract_version", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "occurrence_count >= 1", name="ck_event_quarantine_occurrences"
        ),
        sa.CheckConstraint(
            "id ~ '^[0-9a-f]{64}$'", name="ck_event_quarantine_id"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_quarantine_event_id", "event_quarantine", ["event_id"])
    op.create_index(
        "ix_event_quarantine_last_seen_at", "event_quarantine", ["last_seen_at"]
    )


def downgrade() -> None:
    for table_name in (
        "event_quarantine",
        "event_inbox",
        "borrow_operations",
        "command_receipts",
        "outbox",
        "patrons",
        "loans",
        "books",
    ):
        op.drop_table(table_name)

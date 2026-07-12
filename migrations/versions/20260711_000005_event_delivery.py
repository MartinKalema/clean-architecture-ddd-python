"""Add durable event inbox, quarantine, and retention indexes.

Revision ID: 005
Revises: 004
Create Date: 2026-07-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from migrations.legacy_naive_time import (
    require_safe_revision_002_provenance,
    require_legacy_naive_timezone,
    timezone_sql_literal,
    validate_legacy_timestamp_columns,
)


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    require_safe_revision_002_provenance(connection)
    utc_naive_marker = (
        "(COALESCE(payload::jsonb #>> "
        "'{_legacy_delivery,occurred_at_storage}', '') = 'utc-naive' OR "
        "type = 'library.catalog.book-borrowed.v2.legacy-utc')"
    )
    has_unproven_legacy_timestamps = bool(
        connection.scalar(
            sa.text(
                "SELECT EXISTS ("
                "SELECT 1 FROM outbox WHERE occurred_at IS NOT NULL AND NOT ("
                + utc_naive_marker
                + ")"
                ")"
            )
        )
    )
    legacy_timezone = require_legacy_naive_timezone(
        has_legacy_timestamps=has_unproven_legacy_timestamps,
        revision=revision,
    )
    validate_legacy_timestamp_columns(
        connection,
        table_columns={"outbox": ("occurred_at",)},
        timezone_name=legacy_timezone,
        revision=revision,
        row_filters={"outbox": f"NOT ({utc_naive_marker})"},
    )
    op.alter_column(
        "outbox",
        "occurred_at",
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        postgresql_using=(
            "CASE WHEN "
            + utc_naive_marker
            + " THEN occurred_at AT TIME ZONE 'UTC' ELSE "
            "occurred_at AT TIME ZONE "
            + timezone_sql_literal(legacy_timezone)
            + " END"
        ),
    )
    connection.execute(
        sa.text(
            "UPDATE outbox SET type = 'library.catalog.book-borrowed.v2' "
            "WHERE type = 'library.catalog.book-borrowed.v2.legacy-utc'"
        )
    )
    op.create_table(
        "event_inbox",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("handler_name", sa.String(), nullable=False),
        sa.Column("contract_name", sa.String(), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("causation_id", sa.String(), nullable=True),
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
            "(status = 'processing' AND claim_token IS NOT NULL "
            "AND lease_until IS NOT NULL AND processed_at IS NULL) OR "
            "(status = 'processed' AND claim_token IS NULL "
            "AND lease_until IS NULL AND processed_at IS NOT NULL) OR "
            "(status = 'failed' AND claim_token IS NULL "
            "AND lease_until IS NULL AND processed_at IS NULL)",
            name="ck_event_inbox_status_fields",
        ),
        sa.PrimaryKeyConstraint("event_id", "handler_name"),
    )
    op.create_index(
        "ix_event_inbox_status_lease",
        "event_inbox",
        ["status", "lease_until"],
        unique=False,
    )
    op.create_index(
        "ix_event_inbox_processed_at",
        "event_inbox",
        ["processed_at"],
        unique=False,
    )

    op.create_table(
        "event_quarantine",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("message_key", sa.Text(), nullable=True),
        sa.Column("contract_name", sa.String(), nullable=True),
        sa.Column("contract_version", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "occurrence_count >= 1", name="ck_event_quarantine_occurrences"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_quarantine_event_id",
        "event_quarantine",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_event_quarantine_last_seen_at",
        "event_quarantine",
        ["last_seen_at"],
        unique=False,
    )

    op.create_index(
        "ix_outbox_occurred_at_id",
        "outbox",
        ["occurred_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError(
        "Migration 005 is irreversible: dropping the inbox and quarantine "
        "would erase durable deduplication and replay evidence. Restore a "
        "pre-005 backup instead."
    )

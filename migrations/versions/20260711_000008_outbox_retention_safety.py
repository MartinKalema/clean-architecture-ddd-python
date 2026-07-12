"""Use a database insertion clock for safe outbox retention.

The domain event occurrence time is business data and may legitimately be old
when an event is written or migrated.  It therefore cannot be the retention
clock. Existing rows receive ``inserted_at`` at migration time, which gives a
newly initialized Debezium connector the complete configured retention window.

This revision also removes B-tree indexes that duplicate primary-key indexes
or no longer match any supported query shape.

Revision ID: 008
Revises: 007
Create Date: 2026-07-11
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REDUNDANT_INDEXES = (
    "ix_books_id",
    "ix_books_title",
    "ix_loans_id",
    "ix_patrons_id",
)


def upgrade() -> None:
    # autocommit_block commits this expand step before concurrent index work.
    # Make it idempotent and verify any pre-existing column so an interrupted
    # first run can be retried safely.
    op.execute(
        "ALTER TABLE outbox ADD COLUMN IF NOT EXISTS inserted_at "
        "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
    )
    _verify_inserted_at_column()
    with op.get_context().autocommit_block():
        _ensure_concurrent_index(
            "ix_outbox_inserted_at_id",
            "CREATE INDEX CONCURRENTLY ix_outbox_inserted_at_id "
            "ON outbox (inserted_at, id)",
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_outbox_occurred_at_id"
        )

        for index_name in _REDUNDANT_INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")


def downgrade() -> None:
    raise RuntimeError(
        "Migration 008 is irreversible: removing the database insertion clock "
        "would make outbox retention unsafe. Restore a pre-008 backup instead."
    )


def _verify_inserted_at_column() -> None:
    row = op.get_bind().execute(
        sa.text(
            """
            SELECT data_type, is_nullable, column_default
              FROM information_schema.columns
             WHERE table_schema = current_schema()
               AND table_name = 'outbox'
               AND column_name = 'inserted_at'
            """
        )
    ).mappings().one_or_none()
    if (
        row is None
        or row["data_type"] != "timestamp with time zone"
        or row["is_nullable"] != "NO"
        or row["column_default"] is None
        or not any(
            clock_expression in str(row["column_default"]).lower()
            for clock_expression in ("current_timestamp", "now()")
        )
    ):
        raise RuntimeError(
            "Existing outbox.inserted_at does not match the retention clock contract"
        )


def _ensure_concurrent_index(index_name: str, create_sql: str) -> None:
    bind = op.get_bind()
    query = sa.text(
        """
        SELECT idx.indisvalid
          FROM pg_index AS idx
          JOIN pg_class AS relation ON relation.oid = idx.indexrelid
          JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
         WHERE namespace.nspname = current_schema()
           AND relation.relname = :index_name
        """
    )
    validity = bind.scalar(query, {"index_name": index_name})
    if validity is False:
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"')
        validity = None
    if validity is None:
        op.execute(create_sql)
    if bind.scalar(query, {"index_name": index_name}) is not True:
        raise RuntimeError(f"Concurrent index {index_name} is not valid")

"""Add indexes for bounded, deterministic read-side fallback queries.

Revision ID: 007
Revises: 006
Create Date: 2026-07-11
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # These are production query-plan indexes. SQLite remains a unit-test
        # adapter and does not provide pg_trgm or equivalent operator classes.
        return

    has_pg_trgm = bind.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")
    )
    if has_pg_trgm is not True:
        raise RuntimeError(
            "Migration 007 requires pg_trgm to be provisioned by the database "
            "administrator before the application migrator runs."
        )
    # These may be large production tables. Build and remove indexes outside
    # a transaction so PostgreSQL can use CONCURRENTLY without blocking writes.
    with op.get_context().autocommit_block():
        _ensure_concurrent_index(
            "ix_books_title_trgm",
            "CREATE INDEX CONCURRENTLY ix_books_title_trgm "
            "ON books USING gin (title gin_trgm_ops)",
        )
        _ensure_concurrent_index(
            "ix_books_author_trgm",
            "CREATE INDEX CONCURRENTLY ix_books_author_trgm "
            "ON books USING gin (author gin_trgm_ops)",
        )
        _ensure_concurrent_index(
            "ix_books_title_lower_id",
            "CREATE INDEX CONCURRENTLY ix_books_title_lower_id "
            "ON books (lower(title), id)",
        )
        _ensure_concurrent_index(
            "ix_patrons_registered_at_id",
            "CREATE INDEX CONCURRENTLY ix_patrons_registered_at_id "
            "ON patrons (registered_at, id)",
        )
        _ensure_concurrent_index(
            "ix_loans_patron_borrowed_id",
            "CREATE INDEX CONCURRENTLY ix_loans_patron_borrowed_id "
            "ON loans (patron_id, borrowed_at DESC, id)",
        )
        _ensure_concurrent_index(
            "ix_loans_outstanding_due_date_id",
            "CREATE INDEX CONCURRENTLY ix_loans_outstanding_due_date_id "
            "ON loans (due_date, id) "
            "WHERE status NOT IN ('returned', 'cancelled')",
        )

        # These B-trees do not accelerate the supported operator shapes and
        # only add write amplification.
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_books_author")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_loans_status_due_date")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    with op.get_context().autocommit_block():
        _ensure_concurrent_index(
            "ix_books_author",
            "CREATE INDEX CONCURRENTLY ix_books_author ON books (author)",
        )
        _ensure_concurrent_index(
            "ix_loans_status_due_date",
            "CREATE INDEX CONCURRENTLY ix_loans_status_due_date "
            "ON loans (status, due_date)",
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_loans_outstanding_due_date_id"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_loans_patron_borrowed_id"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_patrons_registered_at_id"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_books_title_lower_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_books_author_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_books_title_trgm")
    # Do not drop pg_trgm: another schema/application may depend on it.


def _ensure_concurrent_index(index_name: str, create_sql: str) -> None:
    """Repair an interrupted concurrent build before considering it present."""
    bind = op.get_bind()
    validity = bind.scalar(
        sa.text(
            """
            SELECT idx.indisvalid
              FROM pg_index AS idx
              JOIN pg_class AS relation ON relation.oid = idx.indexrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = relation.relnamespace
             WHERE namespace.nspname = current_schema()
               AND relation.relname = :index_name
            """
        ),
        {"index_name": index_name},
    )
    if validity is False:
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"')
        validity = None
    if validity is None:
        op.execute(create_sql)
    validity = bind.scalar(
        sa.text(
            """
            SELECT idx.indisvalid
              FROM pg_index AS idx
              JOIN pg_class AS relation ON relation.oid = idx.indexrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = relation.relnamespace
             WHERE namespace.nspname = current_schema()
               AND relation.relname = :index_name
            """
        ),
        {"index_name": index_name},
    )
    if validity is not True:
        raise RuntimeError(f"Concurrent index {index_name} is not valid")

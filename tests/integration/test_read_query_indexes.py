"""Production read fallback indexes are migration-owned and query-shaped."""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_read_side_indexes_exist_with_expected_postgresql_shapes(test_db):
    async with test_db.engine.connect() as connection:
        rows = await connection.execute(
            text(
                "SELECT indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema()"
            )
        )
        definitions = {name: definition for name, definition in rows}

    expected = {
        "ix_books_title_trgm",
        "ix_books_author_trgm",
        "ix_books_title_lower_id",
        "ix_patrons_registered_at_id",
        "ix_loans_patron_borrowed_id",
        "ix_loans_outstanding_due_date_id",
    }
    assert expected <= definitions.keys()
    assert "gin_trgm_ops" in definitions["ix_books_title_trgm"]
    assert "lower((title)::text)" in definitions["ix_books_title_lower_id"]
    assert "WHERE" in definitions["ix_loans_outstanding_due_date_id"]
    assert "ix_outbox_inserted_at_id" in definitions

    redundant = {
        "ix_books_id",
        "ix_books_title",
        "ix_loans_id",
        "ix_patrons_id",
        "ix_outbox_occurred_at_id",
    }
    assert redundant.isdisjoint(definitions)


@pytest.mark.asyncio
async def test_pg_trgm_extension_is_installed(test_db):
    async with test_db.engine.connect() as connection:
        installed = await connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")
        )

    assert installed is True

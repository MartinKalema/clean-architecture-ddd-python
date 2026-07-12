"""Isolation boundary for PostgreSQL-backed integration tests."""
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture(autouse=True)
async def clean_integration_tables(test_db):
    """Make committed UoW tests order-independent and safely repeatable."""
    async def clean() -> None:
        async with test_db.engine.begin() as connection:
            if test_db.db_url.startswith("postgresql"):
                await connection.execute(
                    text(
                        "TRUNCATE TABLE event_inbox, event_quarantine, "
                        "command_receipts, borrow_operations, "
                        "outbox, loans, books, patrons "
                        "RESTART IDENTITY CASCADE"
                    )
                )
            else:  # Local adapter/unit harnesses; committed suite requires PG.
                for table in (
                    "event_inbox",
                    "event_quarantine",
                    "command_receipts",
                    "borrow_operations",
                    "outbox",
                    "loans",
                    "books",
                    "patrons",
                ):
                    await connection.execute(text(f"DELETE FROM {table}"))

    await clean()
    yield
    await clean()

"""Startup contract tests for Alembic-owned database schemas."""
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from src.infrastructure.external.postgresql import (
    DatabaseSchemaMismatchError,
    PostgreSQL,
)


def _repository_head() -> str:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


@pytest.mark.parametrize("revision", ["004", "005", "006", "008"])
def test_identity_and_delivery_contract_migrations_reject_unsafe_downgrade(
    revision,
):
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(config).get_revision(revision)
    assert script is not None

    with pytest.raises(RuntimeError, match="irreversible"):
        script.module.downgrade()


@pytest.mark.asyncio
async def test_schema_verification_rejects_an_uninitialized_database():
    database = PostgreSQL("sqlite:///:memory:")
    try:
        with pytest.raises(DatabaseSchemaMismatchError, match="not initialized"):
            await database.verify_schema_current()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_schema_verification_rejects_a_non_head_revision():
    database = PostgreSQL("sqlite:///:memory:")
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR NOT NULL)")
            )
            await connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES ('003')")
            )

        with pytest.raises(DatabaseSchemaMismatchError, match="database=003"):
            await database.verify_schema_current()
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_schema_verification_accepts_the_repository_head():
    database = PostgreSQL("sqlite:///:memory:")
    try:
        head = _repository_head()
        async with database.engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR NOT NULL)")
            )
            await connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) "
                    "VALUES (:head)"
                ),
                {"head": head},
            )

        await database.verify_schema_current()
    finally:
        await database.dispose()

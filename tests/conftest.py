import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.external.postgresql import PostgreSQL
from src.presentation.api.main import create_app

# Database-backed tests intentionally run only against a PostgreSQL schema
# created by Alembic. A create_all/SQLite fallback would let migration drift
# and PostgreSQL-only constraints escape the test gate.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

@pytest_asyncio.fixture(scope="session")
async def test_db():
    if not TEST_DATABASE_URL:
        pytest.fail(
            "Database-backed tests require TEST_DATABASE_URL pointing to a "
            "PostgreSQL database already migrated with 'alembic upgrade head'"
        )
    db = PostgreSQL(TEST_DATABASE_URL)
    if not db.db_url.startswith("postgresql"):
        await db.dispose()
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    await db.verify_schema_current()
    yield db
    await db.dispose()

@pytest_asyncio.fixture
async def db_session(test_db) -> AsyncGenerator[AsyncSession, None]:
    connection = await test_db.engine.connect()
    transaction = await connection.begin()

    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session

    await transaction.rollback()
    await connection.close()

@pytest_asyncio.fixture
async def client(test_db) -> AsyncGenerator[AsyncClient, None]:
    # The factory composes the app (container build + etcd config load)
    # on invocation; importing the module has no side effects
    app = create_app()
    container = app.container

    container.postgresql.override(providers.Object(test_db))

    # Mock external services
    from unittest.mock import AsyncMock
    container.event_dispatcher.override(providers.Object(AsyncMock()))
    container.email_service.override(providers.Object(AsyncMock()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    container.unwire()

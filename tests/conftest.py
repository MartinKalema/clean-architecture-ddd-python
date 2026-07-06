from typing import AsyncGenerator

import pytest_asyncio
from dependency_injector import providers
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.external.postgresql import PostgreSQL
from src.presentation.api.main import create_app

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
async def test_db():
    db = PostgreSQL(TEST_DATABASE_URL)
    await db.init_models()
    yield db
    await db.engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_db) -> AsyncGenerator[AsyncSession, None]:
    connection = await test_db.engine.connect()
    transaction = await connection.begin()

    session_factory = async_sessionmaker(bind=connection, class_=AsyncSession, expire_on_commit=False)
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

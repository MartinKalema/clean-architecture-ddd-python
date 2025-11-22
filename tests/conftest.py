import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.external.database import Database
from src.presentation.api.main import app
from src.container import Container
from dependency_injector import providers

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
async def test_db():
    db = Database(TEST_DATABASE_URL)
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
    container = Container()
    container.database.override(providers.Object(test_db))
    
    # Mock external services
    from unittest.mock import AsyncMock
    container.event_dispatcher.override(providers.Object(AsyncMock()))
    container.email_service.override(providers.Object(AsyncMock()))
    
    app.container = container
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    container.database.reset_override()
    container.event_dispatcher.reset_override()
    container.email_service.reset_override()

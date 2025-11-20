import pytest
import pytest_asyncio
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.external.database import Base
from src.presentation.api.main import app
from src.container import Container
from dependency_injector import providers

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    connection = await db_engine.connect()
    transaction = await connection.begin()
    
    session_factory = async_sessionmaker(bind=connection, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        
    await transaction.rollback()
    await connection.close()

@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    # Override the container's session factory with the test session
    # Note: For the factory pattern in repository, we need to mock the factory to return our test session
    # This is a bit tricky with the current implementation where repository creates its own session from a factory.
    # A better approach for integration tests might be to let the repository use a factory that returns our test session.
    
    # However, since we are using dependency injection, we can override the provider.
    
    # Create a factory that returns the active test session
    # But async_sessionmaker returns a new session. 
    # We need the repository to use a factory that yields our `db_session` or connects to our `connection`.
    
    # Simplified approach for E2E:
    # We override the session_factory in the container to return a factory that binds to our test engine.
    
    container = Container()
    
    # For E2E, we want the app to use a session factory bound to our test DB.
    # We can't easily share the *exact* same session object across requests in E2E 
    # because the app creates a new session per request (or per repo op).
    # So we override the session_factory to point to the test DB engine.
    
    test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    test_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    
    container.session_factory.override(providers.Callable(lambda: test_session_factory))
    app.container = container
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    container.session_factory.reset_override()

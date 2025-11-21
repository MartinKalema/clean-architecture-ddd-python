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
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    # Create a session factory bound to the SHARED db_engine
    test_session_factory = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    
    container = Container()
    container.session_factory.override(providers.Callable(lambda: test_session_factory))
    app.container = container
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
        
    container.session_factory.reset_override()

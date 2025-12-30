import pytest
from click.testing import CliRunner
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.container import Container
from src.infrastructure.external.postgresql import Base
from src.presentation.cli.main import cli

# Note: Testing CLI with real DB/Async in this setup is complex because CliRunner is synchronous
# and our commands use asyncio.run(). 
# Also, dependency injection wiring might conflict if not handled carefully.
# For this E2E test, we'll mock the container or use a separate runner setup if needed.
# However, since we wired the container in main.py, we need to ensure it uses the test DB.

# Given the complexity of injecting test DB into the CLI which wires its own container,
# we might skip deep DB verification here or rely on the fact that we can override the container 
# globally if we were running in the same process. 
# But CliRunner runs the command as a callable.

# Let's try a basic smoke test that the commands run. 
# Ideally, we would override the Container.session_factory before invoking the CLI.


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
def cli_runner():
    return CliRunner()

@pytest.fixture
def setup_cli_db():
    # Setup a test DB and override the container
    # This is synchronous because pytest fixtures for CliRunner are typically sync
    # But we need async setup. 
    # We can use asyncio.run here for setup.
    
    import asyncio
    
    async def init_db():
        engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return engine

    engine = asyncio.run(init_db())
    
    container = Container()
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    container.session_factory.override(session_factory)
    
    # We need to ensure the CLI uses THIS container.
    # The CLI commands use @inject which uses the global Container instance if wired.
    # We need to wire this container instance.
    
    container.wire(modules=[
        "src.presentation.cli.commands.add_book_command",
        "src.presentation.cli.commands.list_books_command",
        "src.presentation.cli.commands.borrow_book_command"
    ])
    
    yield
    
    container.unwire()

def test_cli_add_and_list(cli_runner, setup_cli_db):
    # Add
    result = cli_runner.invoke(cli, ["add", "CLI E2E", "Tester"])
    assert result.exit_code == 0
    assert "Book added: CLI E2E" in result.output
    
    # List
    result = cli_runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "CLI E2E" in result.output

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base


class Database:
    def __init__(self, db_url: str):
        # Convert to async driver URL
        self.db_url = self._to_async_url(db_url)

        # Build engine kwargs based on database type
        engine_kwargs = {}
        if "sqlite" in self.db_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        self.engine = create_async_engine(self.db_url, **engine_kwargs)
        self.session_factory = async_sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            class_=AsyncSession
        )

    def _to_async_url(self, url: str) -> str:
        """Convert database URL to use async driver."""
        if url.startswith("sqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://")
        elif url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://")
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://")
        return url

    async def init_models(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


Base = declarative_base()

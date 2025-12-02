from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base


class Database:
    def __init__(
        self,
        db_url: str,
        pool_size: int = 20,
        max_overflow: int = 30,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
    ):
        """
        Initialize database with connection pooling.

        Args:
            db_url: Database connection URL
            pool_size: Number of connections to keep in pool (default: 20)
            max_overflow: Max connections beyond pool_size (default: 30)
                          Total max connections = pool_size + max_overflow = 50
            pool_timeout: Seconds to wait for available connection (default: 30)
            pool_recycle: Recycle connections after N seconds (default: 1800)
        """
        self.db_url = self._to_async_url(db_url)

        # Build engine kwargs based on database type
        engine_kwargs: Dict[str, Any] = {
            "pool_pre_ping": True,  # Verify connections before use
        }

        if "sqlite" in self.db_url:
            # SQLite doesn't support connection pooling the same way
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            # PostgreSQL connection pool settings
            engine_kwargs.update({
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_timeout": pool_timeout,
                "pool_recycle": pool_recycle,
            })
            # Disable statement cache for PgBouncer compatibility
            if "postgresql" in self.db_url:
                engine_kwargs["connect_args"] = {"statement_cache_size": 0}

        self.engine = create_async_engine(self.db_url, **engine_kwargs)
        self.session_factory = async_sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,  # Prevent lazy loading issues after commit
        )

    def _to_async_url(self, url: str) -> str:
        """Convert database URL to use async driver."""
        if url.startswith("sqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://")
        elif url.startswith("postgresql://") or url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://").replace("postgresql://", "postgresql+asyncpg://")
        return url

    async def init_models(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self):
        """Dispose of the connection pool."""
        await self.engine.dispose()


Base = declarative_base()

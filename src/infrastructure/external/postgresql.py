from pathlib import Path
from typing import Any, Dict

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base


class DatabaseSchemaMismatchError(RuntimeError):
    """Raised when the database was not migrated to this release's schema."""


class PostgreSQL:
    def __init__(
        self,
        db_url: str,
        pool_size: int = 20,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
    ):
        """
        Initialize database with connection pooling.

        Args:
            db_url: Database connection URL
            pool_size: Number of connections to keep in pool (default: 20)
            max_overflow: Max connections beyond pool_size (default: 10)
            pool_timeout: Seconds to wait for available connection (default: 30)
            pool_recycle: Recycle connections after N seconds (default: 1800)
        """
        if not isinstance(db_url, str) or not db_url.strip():
            raise ValueError("db_url must be a non-blank string")
        if isinstance(pool_size, bool) or not 1 <= pool_size <= 100:
            raise ValueError("pool_size must be between 1 and 100")
        if isinstance(max_overflow, bool) or not 0 <= max_overflow <= 100:
            raise ValueError("max_overflow must be between 0 and 100")
        if pool_size + max_overflow > 100:
            raise ValueError("pool_size + max_overflow must not exceed 100")
        if isinstance(pool_timeout, bool) or not 1 <= pool_timeout <= 300:
            raise ValueError("pool_timeout must be between 1 and 300 seconds")
        if isinstance(pool_recycle, bool) or not 0 <= pool_recycle <= 86_400:
            raise ValueError("pool_recycle must be between 0 and 86400 seconds")

        self.db_url = self._to_async_url(db_url)

        engine_kwargs: Dict[str, Any] = {
            "pool_pre_ping": True,
        }

        if "sqlite" in self.db_url:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs.update({
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_timeout": pool_timeout,
                "pool_recycle": pool_recycle,
            })
            if "postgresql" in self.db_url:
                engine_kwargs["connect_args"] = {"statement_cache_size": 0}

        self.engine = create_async_engine(self.db_url, **engine_kwargs)
        self.session_factory = async_sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def _to_async_url(self, url: str) -> str:
        """Convert database URL to use async driver."""
        if url.startswith("sqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://")
        elif url.startswith("postgresql://") or url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://").replace(
                "postgresql://", "postgresql+asyncpg://"
            )
        return url

    async def verify_schema_current(
        self,
        alembic_config_path: str | Path | None = None,
    ) -> None:
        """Fail unless the database revision exactly matches Alembic head.

        Application instances never migrate the database themselves. The
        deployment migrator owns that control-plane operation; instances only
        enforce its postcondition before accepting traffic.
        """
        project_root = Path(__file__).resolve().parents[3]
        config_path = Path(alembic_config_path or project_root / "alembic.ini").resolve()
        if not config_path.is_file():
            raise DatabaseSchemaMismatchError(
                f"Alembic configuration was not found at {config_path}"
            )

        alembic_config = Config(str(config_path))
        # ``script_location`` in alembic.ini is intentionally relative for the
        # CLI. Resolve it here so startup does not depend on its working dir.
        script_location = alembic_config.get_main_option("script_location")
        if not script_location:
            raise DatabaseSchemaMismatchError("Alembic script_location is not configured")
        script_path = Path(script_location)
        if not script_path.is_absolute():
            script_path = config_path.parent / script_path
        alembic_config.set_main_option("script_location", str(script_path.resolve()))
        repository_heads = set(ScriptDirectory.from_config(alembic_config).get_heads())
        if not repository_heads:
            raise DatabaseSchemaMismatchError("The Alembic repository has no head revision")

        try:
            async with self.engine.connect() as connection:
                result = await connection.execute(text("SELECT version_num FROM alembic_version"))
                database_heads = set(result.scalars().all())
        except SQLAlchemyError as exc:
            raise DatabaseSchemaMismatchError(
                "Database schema is not initialized; run 'alembic upgrade head'"
            ) from exc

        if database_heads != repository_heads:
            database_revision = ", ".join(sorted(database_heads)) or "<none>"
            repository_revision = ", ".join(sorted(repository_heads))
            raise DatabaseSchemaMismatchError(
                "Database schema revision mismatch: "
                f"database={database_revision}, repository={repository_revision}. "
                "Run 'alembic upgrade head' before starting the application."
            )

    async def ping(self) -> None:
        """Verify connectivity; raises if the database is unreachable."""
        async with self.session_factory() as session:
            await session.execute(text("SELECT 1"))

    async def dispose(self):
        """Dispose of the connection pool."""
        await self.engine.dispose()


Base = declarative_base()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
class Database:
    def __init__(self, db_url: str):
        # Ensure the URL uses the async driver
        self.db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")
        self.engine = create_async_engine(
            self.db_url, 
            connect_args={"check_same_thread": False}
        )
        self.session_factory = async_sessionmaker(
            autocommit=False, 
            autoflush=False, 
            bind=self.engine, 
            class_=AsyncSession
        )

    async def init_models(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

Base = declarative_base()

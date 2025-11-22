from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from src.domain.interfaces.unit_of_work import UnitOfWork
from src.infrastructure.repositories.sql_book_repository import SQLBookRepository

class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self.session_factory()
        self.books = SQLBookRepository(self._session)
        return self

    async def __aexit__(self, exc_type, _exc_val, _exc_tb):
        if exc_type:
            await self.rollback()
        await self._session.close()
        self._session = None

    async def commit(self):
        if self._session:
            await self._session.commit()

    async def rollback(self):
        if self._session:
            await self._session.rollback()

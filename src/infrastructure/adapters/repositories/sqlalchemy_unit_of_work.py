from typing import Dict
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.catalog import Book
from src.domain.shared_kernel import EventDispatcher
from src.infrastructure.adapters.repositories.sql_book_repository import SQLBookRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], event_dispatcher: EventDispatcher = None):
        self.session_factory = session_factory
        self.event_dispatcher = event_dispatcher
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self.session_factory()
        self.identity_map: Dict[str, Book] = {}
        self.books = SQLBookRepository(self._session, self.identity_map)
        return self

    async def __aexit__(self, exc_type, _exc_val, _exc_tb):
        if exc_type:
            await self.rollback()
        await self._session.close()
        self._session = None

    async def commit(self):
        if not self._session:
            return

        # Collect events before commit
        events = self._collect_events()

        await self._session.commit()

        # Dispatch events after successful commit
        if self.event_dispatcher:
            for event in events:
                await self.event_dispatcher.dispatch(event)

    async def rollback(self):
        if self._session:
            await self._session.rollback()

    def _collect_events(self) -> list:
        events = []
        if not hasattr(self, 'identity_map'):
            return events

        for aggregate in self.identity_map.values():
            events.extend(aggregate.get_domain_events())
            aggregate.clear_events()
        return events

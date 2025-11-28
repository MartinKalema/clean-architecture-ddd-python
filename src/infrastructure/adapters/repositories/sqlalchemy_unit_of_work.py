from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from src.infrastructure.adapters.repositories.sql_book_repository import SQLBookRepository
from src.infrastructure.adapters.outbox import OutboxRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from src.domain.catalog import Book
    from src.domain.shared_kernel import EventDispatcher


class SqlAlchemyUnitOfWork:
    """
    Unit of Work pattern implementation with Transactional Outbox.

    Events are stored in the outbox table within the same transaction as
    the aggregate changes, ensuring they are never lost. A background
    processor (OutboxProcessor) then dispatches them to the message broker.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_dispatcher: Optional[EventDispatcher] = None,
        use_outbox: bool = True
    ):
        self.session_factory = session_factory
        self.event_dispatcher = event_dispatcher
        self.use_outbox = use_outbox
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self.session_factory()
        self.identity_map: Dict[str, Book] = {}
        self.books = SQLBookRepository(self._session, self.identity_map)
        self._outbox = OutboxRepository(self._session) if self.use_outbox else None
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

        # Store events in outbox (same transaction as aggregate changes)
        if self.use_outbox and self._outbox and events:
            await self._outbox.add_many(events)

        await self._session.commit()

        # If not using outbox, dispatch events directly (legacy behavior)
        if not self.use_outbox and self.event_dispatcher:
            for event in events:
                try:
                    await self.event_dispatcher.dispatch(event)
                except Exception:
                    # Log but don't fail the commit - events are lost in this mode
                    pass

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

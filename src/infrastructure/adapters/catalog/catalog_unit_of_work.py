"""
Catalog Unit of Work - Infrastructure implementation.

Implements: ICatalogUnitOfWork
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.infrastructure.adapters.catalog.book_command_repository import (
    BookCommandRepository,
)
from src.infrastructure.adapters.outbox import OutboxRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.domain.catalog import Book
    from src.domain.shared_kernel import IEventDispatcher, ILogger


class CatalogUnitOfWork:
    """
    Unit of Work pattern implementation with Transactional Outbox.

    Events are stored in the outbox table within the same transaction as
    the aggregate changes, ensuring they are never lost. A background
    processor (OutboxProcessor) then dispatches them to the message broker.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_dispatcher: Optional[IEventDispatcher] = None,
        use_outbox: bool = True,
        logger: Optional[ILogger] = None
    ):
        self.session_factory = session_factory
        self.event_dispatcher = event_dispatcher
        self.use_outbox = use_outbox
        self.logger = logger
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "CatalogUnitOfWork":
        self._session = self.session_factory()
        self.identity_map: Dict[str, Book] = {}
        self.books = BookCommandRepository(self._session, self.identity_map)
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

        events = self._collect_events()

        if self.use_outbox and self._outbox and events:
            await self._outbox.add_many(events)

        await self._session.commit()

        if not self.use_outbox and self.event_dispatcher:
            for event in events:
                try:
                    await self.event_dispatcher.dispatch(event)
                except Exception as e:
                    event_name = type(event).__name__
                    if self.logger:
                        self.logger.error(
                            f"Failed to dispatch event {event_name}: {e}",
                            exception=e
                        )
                    else:
                        raise

    async def rollback(self):
        if self._session:
            await self._session.rollback()

    def _collect_events(self) -> List[Any]:
        events: List[Any] = []
        if not hasattr(self, 'identity_map'):
            return events

        for aggregate in self.identity_map.values():
            events.extend(aggregate.get_domain_events())
            aggregate.clear_events()
        return events

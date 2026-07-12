"""
Catalog Unit of Work - Infrastructure implementation.

Implements the application-owned catalog transaction port.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from sqlalchemy.exc import IntegrityError

from src.application.exceptions import IdempotencyKeyConflictException
from src.infrastructure.adapters.application_state import (
    BorrowOperationRepository,
    CommandReceiptRepository,
)
from src.infrastructure.adapters.catalog.book_command_repository import (
    BookCommandRepository,
)
from src.infrastructure.adapters.outbox import OutboxMessageModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.application.ports import ILogger
    from src.domain.catalog import Book


class CatalogUnitOfWork:
    """
    Unit of Work pattern implementation for Catalog bounded context.

    Manages transactions and tracks aggregates within a session.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: Optional[ILogger] = None
    ):
        self.session_factory = session_factory
        self.logger = logger
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "CatalogUnitOfWork":
        self._session = self.session_factory()
        self.identity_map: Dict[str, Book] = {}
        self.dirty_ids: set[str] = set()
        self.books = BookCommandRepository(
            self._session, self.identity_map, self.dirty_ids
        )
        self.command_receipts = CommandReceiptRepository(self._session)
        self.borrow_operations = BorrowOperationRepository(self._session)
        return self

    async def __aexit__(self, exc_type, _exc_val, _exc_tb):
        if exc_type:
            await self.rollback()
        await self._session.close()
        self._session = None

    async def commit(self):
        if self._session:
            self._stage_domain_events()
            try:
                await self._session.commit()
            except IntegrityError as error:
                await self.rollback()
                if "command_receipts" in str(error.orig):
                    receipt = next(iter(self.command_receipts.pending), None)
                    raise IdempotencyKeyConflictException(
                        receipt.idempotency_key if receipt else "unknown",
                        "another request with this key committed concurrently; retry",
                    ) from error
                raise
            else:
                self._clear_committed_events()

    def _stage_domain_events(self) -> None:
        """
        Write pending domain events to the transactional outbox.

        Runs inside the same transaction as the aggregate changes, so the
        state change and its events commit (or roll back) atomically.
        Debezium picks the rows up from the WAL and publishes them to Kafka.
        """
        assert self._session is not None
        for aggregate_id in self.dirty_ids:
            aggregate = self.identity_map[aggregate_id]
            for event in aggregate.get_domain_events():
                self._session.add(
                    OutboxMessageModel.from_domain_event(
                        event,
                        aggregate_type="book",
                        aggregate_id=aggregate.id.value,
                    )
                )

    def _clear_committed_events(self) -> None:
        for aggregate_id in self.dirty_ids:
            self.identity_map[aggregate_id].clear_events()
        self.dirty_ids.clear()

    async def rollback(self):
        if self._session:
            await self._session.rollback()

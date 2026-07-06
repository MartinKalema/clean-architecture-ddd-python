"""
Loan Unit of Work - Infrastructure implementation.

Implements: ILoanUnitOfWork
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from sqlalchemy.exc import IntegrityError

from src.domain.lending.exceptions import BookNotAvailableException
from src.infrastructure.adapters.lending.loan_command_repository import (
    LoanCommandRepository,
)
from src.infrastructure.adapters.outbox import OutboxMessageModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.domain.lending import Loan
    from src.domain.shared_kernel import ILogger


class LoanUnitOfWork:
    """
    Unit of Work pattern implementation for Lending bounded context.

    Manages transactions and tracks aggregates within a session.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: Optional[ILogger] = None,
    ):
        self.session_factory = session_factory
        self.logger = logger
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "LoanUnitOfWork":
        self._session = self.session_factory()
        self.identity_map: Dict[str, Loan] = {}
        self.loans = LoanCommandRepository(self._session, self.identity_map)
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
            except IntegrityError as e:
                # Translate the framework exception at the boundary: the
                # partial unique index (one active loan per book) losing a
                # race is a domain fact, and callers must not need
                # SQLAlchemy to understand it
                await self.rollback()
                if "ix_loans_active_book_unique" in str(e.orig):
                    book_id = next(
                        (
                            loan.catalog_book_id
                            for loan in self.identity_map.values()
                        ),
                        "unknown",
                    )
                    raise BookNotAvailableException(book_id) from e
                raise

    def _stage_domain_events(self) -> None:
        """
        Write pending domain events to the transactional outbox.

        Runs inside the same transaction as the aggregate changes, so the
        state change and its events commit (or roll back) atomically.
        Debezium picks the rows up from the WAL and publishes them to Kafka.
        """
        assert self._session is not None
        for aggregate in self.identity_map.values():
            for event in aggregate.get_domain_events():
                self._session.add(
                    OutboxMessageModel.from_domain_event(
                        event,
                        aggregate_type=type(aggregate).__name__.lower(),
                        aggregate_id=aggregate.id.value,
                    )
                )
            aggregate.clear_events()

    async def rollback(self):
        if self._session:
            await self._session.rollback()

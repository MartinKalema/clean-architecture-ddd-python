"""
Loan Unit of Work - Infrastructure implementation.

Implements the application-owned lending transaction port.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from sqlalchemy.exc import IntegrityError

from src.application.exceptions import IdempotencyKeyConflictException
from src.infrastructure.adapters.borrowing_fence import acquire_borrowing_fence
from src.infrastructure.adapters.application_state import CommandReceiptRepository
from src.domain.lending.exceptions import ConcurrentLoanCreationException
from src.infrastructure.adapters.lending.loan_command_repository import (
    LoanCommandRepository,
)
from src.infrastructure.adapters.outbox import OutboxMessageModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.application.ports import ILogger
    from src.domain.lending import Loan


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
        self.dirty_ids: set[str] = set()
        self.loans = LoanCommandRepository(
            self._session, self.identity_map, self.dirty_ids
        )
        self.command_receipts = CommandReceiptRepository(self._session)
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
                # Translate either uniqueness race at the persistence
                # boundary. The application must first check whether the
                # winning row belongs to this exact reservation; treating an
                # ambiguous conflict as "book unavailable" could compensate a
                # valid duplicate delivery.
                await self.rollback()
                constraint_name = self._constraint_name(e)
                constraint = f"{constraint_name} {e.orig}"
                if "command_receipts" in constraint:
                    receipt = next(iter(self.command_receipts.pending), None)
                    raise IdempotencyKeyConflictException(
                        receipt.idempotency_key if receipt else "unknown",
                        "another request with this key committed concurrently; retry",
                    ) from e
                if (
                    "ix_loans_outstanding_book_unique" in constraint
                    or "ix_loans_reservation_id_unique" in constraint
                    # SQLite reports columns rather than index names.
                    or "UNIQUE constraint failed: loans.catalog_book_id"
                    in constraint
                    or "UNIQUE constraint failed: loans.reservation_id"
                    in constraint
                ):
                    loan = next(iter(self.identity_map.values()), None)
                    raise ConcurrentLoanCreationException(
                        reservation_id=(
                            loan.reservation_id.value if loan else "unknown"
                        ),
                        book_id=(loan.catalog_book_id if loan else "unknown"),
                    ) from e
                raise
            else:
                self._clear_committed_events()

    async def acquire_borrowing_fence(self, patron_id: str) -> None:
        """Serialize final Lending admission against Patron policy changes."""
        assert self._session is not None
        await acquire_borrowing_fence(self._session, patron_id)

    @staticmethod
    def _constraint_name(error: IntegrityError) -> str:
        """Extract a driver diagnostic name, with text fallback at the caller."""
        candidates = (
            error.orig,
            getattr(error.orig, "__cause__", None),
            getattr(error.orig, "__context__", None),
        )
        for candidate in candidates:
            if candidate is None:
                continue
            name = getattr(candidate, "constraint_name", None)
            if name:
                return str(name)
            diagnostic = getattr(candidate, "diag", None)
            name = getattr(diagnostic, "constraint_name", None)
            if name:
                return str(name)
        return ""

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
                        aggregate_type="loan",
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

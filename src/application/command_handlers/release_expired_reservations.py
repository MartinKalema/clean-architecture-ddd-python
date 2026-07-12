"""
Release Expired Reservations Command - CQRS Command Side.

Semantic locks can leak: if the borrow saga dies between reserving the
book and confirming (or releasing) it, the book stays RESERVED forever —
unavailable, but with no loan. This command releases one bounded batch of
reservations older than the TTL. The worker invokes it repeatedly so every
committed batch crosses the application decorator and invalidates caches.

The TTL must be comfortably above worst-case event latency to avoid needless
compensation. Exact reservation fencing makes a race safe: a late loan can
only be cancelled for the reservation that the reaper released.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from src.application.ports import BorrowOperationStatus

if TYPE_CHECKING:
    from src.application.ports import ICatalogApplicationUnitOfWork, IClock, ILogger


@dataclass(frozen=True)
class ReleaseExpiredReservationsCommand:
    """Command to release reservations older than the TTL."""
    ttl_seconds: int
    batch_size: int = 100


@dataclass(frozen=True)
class ReleaseExpiredReservationsResult:
    """Result of the expiry sweep."""
    released_count: int
    batch_full: bool


class ReleaseExpiredReservationsHandler:
    """Handles the ReleaseExpiredReservationsCommand."""

    def __init__(self, uow: ICatalogApplicationUnitOfWork, logger: ILogger, clock: IClock):
        self.uow = uow
        self.logger = logger
        self.clock = clock

    async def handle(
        self, command: ReleaseExpiredReservationsCommand
    ) -> ReleaseExpiredReservationsResult:
        if command.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if not 1 <= command.batch_size <= 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        cutoff = self.clock.now() - timedelta(seconds=command.ttl_seconds)
        async with self.uow:
            expired = await self.uow.books.find_expired_reservations(
                cutoff, limit=command.batch_size
            )
            released_count = 0
            for book in expired:
                assert book.reservation_id is not None
                assert book.reserved_patron_id is not None
                changed = book.release(
                    reservation_id=book.reservation_id,
                    reservation_generation=book.reservation_generation,
                    patron_id=book.reserved_patron_id,
                    reason=(
                        f"reservation expired after {command.ttl_seconds}s "
                        f"without loan confirmation"
                    ),
                )
                if not changed:
                    continue
                await self.uow.books.update(book)
                await self.uow.borrow_operations.transition(
                    book.reservation_id.value,
                    BorrowOperationStatus.RELEASED,
                    book_id=book.id.value,
                    patron_id=book.reserved_patron_id,
                    reservation_generation=book.reservation_generation,
                    failure_reason="reservation expired",
                    updated_at=self.clock.now(),
                )
                released_count += 1
                self.logger.warning(
                    f"Released expired reservation: {book.title.value} "
                    f"({book.id.value})"
                )

            if expired:
                await self.uow.commit()

        return ReleaseExpiredReservationsResult(
            released_count=released_count,
            batch_full=len(expired) == command.batch_size,
        )

"""
Release Expired Reservations Command - CQRS Command Side.

Semantic locks can leak: if the borrow saga dies between reserving the
book and confirming (or releasing) it, the book stays RESERVED forever —
unavailable, but with no loan. This command is the lock's expiry: it
releases every reservation older than the TTL.

The TTL must be comfortably above worst-case event latency, or the reaper
races the saga: a released reservation whose loan event then arrives
leaves a loan for a book the catalog gave back.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.catalog import ICatalogUnitOfWork
    from src.domain.shared_kernel import ILogger


@dataclass(frozen=True)
class ReleaseExpiredReservationsCommand:
    """Command to release reservations older than the TTL."""
    ttl_seconds: int


@dataclass(frozen=True)
class ReleaseExpiredReservationsResult:
    """Result of the expiry sweep."""
    released_count: int


class ReleaseExpiredReservationsHandler:
    """Handles the ReleaseExpiredReservationsCommand."""

    def __init__(self, uow: ICatalogUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(
        self, command: ReleaseExpiredReservationsCommand
    ) -> ReleaseExpiredReservationsResult:
        cutoff = datetime.now() - timedelta(seconds=command.ttl_seconds)

        async with self.uow:
            expired = await self.uow.books.find_expired_reservations(cutoff)

            for book in expired:
                book.release(
                    f"reservation expired after {command.ttl_seconds}s "
                    f"without loan confirmation"
                )
                await self.uow.books.update(book)
                self.logger.warning(
                    f"Released expired reservation: {book.title.value} "
                    f"({book.id.value})"
                )

            if expired:
                await self.uow.commit()

            return ReleaseExpiredReservationsResult(released_count=len(expired))

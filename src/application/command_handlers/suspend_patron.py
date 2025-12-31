"""
Suspend Patron Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.patron.exceptions import PatronNotFoundException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.adapters.patron import PatronUnitOfWork


@dataclass(frozen=True)
class SuspendPatronCommand:
    """Command to suspend a patron."""
    patron_id: str
    reason: str


@dataclass(frozen=True)
class SuspendPatronResult:
    """Result of suspending a patron."""
    id: str
    is_suspended: bool
    reason: str


class SuspendPatronHandler:
    """Handles patron suspension."""

    def __init__(self, uow: PatronUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: SuspendPatronCommand) -> SuspendPatronResult:
        async with self.uow:
            patron = await self.uow.patrons.get_by_id(command.patron_id)
            if not patron:
                raise PatronNotFoundException(command.patron_id)

            patron.suspend(command.reason)

            await self.uow.patrons.update(patron)
            await self.uow.commit()

            self.logger.info(f"Patron suspended: {patron.id.value}")

            return SuspendPatronResult(
                id=patron.id.value,
                is_suspended=patron.is_suspended,
                reason=patron.suspended_reason,
            )

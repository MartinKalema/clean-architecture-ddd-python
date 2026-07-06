"""
Reinstate Patron Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.patron.exceptions import PatronNotFoundException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.domain.patron import IPatronUnitOfWork


@dataclass(frozen=True)
class ReinstatePatronCommand:
    """Command to reinstate a suspended patron."""
    patron_id: str


@dataclass(frozen=True)
class ReinstatePatronResult:
    """Result of reinstating a patron."""
    id: str
    is_suspended: bool


class ReinstatePatronHandler:
    """Handles patron reinstatement."""

    def __init__(self, uow: IPatronUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: ReinstatePatronCommand) -> ReinstatePatronResult:
        async with self.uow:
            patron = await self.uow.patrons.get_by_id(command.patron_id)
            if not patron:
                raise PatronNotFoundException(command.patron_id)

            patron.reinstate()

            await self.uow.patrons.update(patron)
            await self.uow.commit()

            self.logger.info(f"Patron reinstated: {patron.id.value}")

            return ReinstatePatronResult(
                id=patron.id.value,
                is_suspended=patron.is_suspended,
            )

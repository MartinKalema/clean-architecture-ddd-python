"""
Reinstate Patron Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.ports import (
    CommandReceipt,
    IdempotencyKey,
    command_fingerprint,
    require_matching_receipt,
)
from src.domain.patron.exceptions import PatronNotFoundException

from .patron_snapshot import PatronSnapshot

if TYPE_CHECKING:
    from src.application.ports import ILogger, IPatronApplicationUnitOfWork


@dataclass(frozen=True)
class ReinstatePatronCommand:
    """Command to reinstate a suspended patron."""
    patron_id: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ReinstatePatronResult(PatronSnapshot):
    """Result of reinstating a patron."""


class ReinstatePatronHandler:
    """Handles patron reinstatement."""

    def __init__(self, uow: IPatronApplicationUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: ReinstatePatronCommand) -> ReinstatePatronResult:
        patron_id = command.patron_id.strip()
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        request_hash = command_fingerprint({"patron_id": patron_id})
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "patron.reinstate", key.value
                )
                if receipt:
                    return ReinstatePatronResult.from_mapping(
                        require_matching_receipt(receipt, request_hash)
                    )

            await self.uow.acquire_borrowing_fence(patron_id)
            patron = await self.uow.patrons.get_by_id(patron_id)
            if not patron:
                raise PatronNotFoundException(patron_id)

            patron.reinstate()

            await self.uow.patrons.update(patron)
            result = ReinstatePatronResult.from_patron(patron)
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="patron.reinstate",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response=result.__dict__,
                    )
                )
            await self.uow.commit()

            self.logger.info(f"Patron reinstated: {patron.id.value}")

            return result

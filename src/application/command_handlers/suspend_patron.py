"""
Suspend Patron Command Handler.
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
class SuspendPatronCommand:
    """Command to suspend a patron."""
    patron_id: str
    reason: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SuspendPatronResult(PatronSnapshot):
    """Result of suspending a patron."""


class SuspendPatronHandler:
    """Handles patron suspension."""

    def __init__(self, uow: IPatronApplicationUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: SuspendPatronCommand) -> SuspendPatronResult:
        patron_id = command.patron_id.strip()
        reason = " ".join(command.reason.split())
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        request_hash = command_fingerprint(
            {"patron_id": patron_id, "reason": reason}
        )
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "patron.suspend", key.value
                )
                if receipt:
                    return SuspendPatronResult.from_mapping(
                        require_matching_receipt(receipt, request_hash)
                    )

            await self.uow.acquire_borrowing_fence(patron_id)
            patron = await self.uow.patrons.get_by_id(patron_id)
            if not patron:
                raise PatronNotFoundException(patron_id)

            patron.suspend(reason)

            await self.uow.patrons.update(patron)
            result = SuspendPatronResult.from_patron(patron)
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="patron.suspend",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response=result.__dict__,
                    )
                )
            await self.uow.commit()

            self.logger.info(f"Patron suspended: {patron.id.value}")

            return result

"""
Upgrade Patron Tier Command Handler.
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
from src.domain.patron.value_objects import MembershipTier

from .patron_snapshot import PatronSnapshot

if TYPE_CHECKING:
    from src.application.ports import ILogger, IPatronApplicationUnitOfWork


@dataclass(frozen=True)
class UpgradePatronTierCommand:
    """Command to upgrade a patron's membership tier."""
    patron_id: str
    new_tier: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class UpgradePatronTierResult(PatronSnapshot):
    """Result of upgrading patron tier."""


class UpgradePatronTierHandler:
    """Handles patron tier upgrades."""

    def __init__(self, uow: IPatronApplicationUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: UpgradePatronTierCommand) -> UpgradePatronTierResult:
        patron_id = command.patron_id.strip()
        new_tier = MembershipTier(command.new_tier.strip().lower())
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        request_hash = command_fingerprint(
            {"patron_id": patron_id, "new_tier": new_tier.value}
        )
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "patron.upgrade_tier", key.value
                )
                if receipt:
                    return UpgradePatronTierResult.from_mapping(
                        require_matching_receipt(receipt, request_hash)
                    )

            await self.uow.acquire_borrowing_fence(patron_id)
            patron = await self.uow.patrons.get_by_id(patron_id)
            if not patron:
                raise PatronNotFoundException(patron_id)

            patron.upgrade_tier(new_tier)

            await self.uow.patrons.update(patron)
            result = UpgradePatronTierResult.from_patron(patron)
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="patron.upgrade_tier",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response=result.__dict__,
                    )
                )
            await self.uow.commit()

            self.logger.info(f"Patron tier upgraded: {patron.id.value} -> {new_tier.value}")

            return result

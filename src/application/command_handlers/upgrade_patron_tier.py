"""
Upgrade Patron Tier Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.patron.exceptions import PatronNotFoundException
from src.domain.patron.value_objects import MembershipTier

if TYPE_CHECKING:
    from src.domain.shared_kernel import Logger
    from src.infrastructure.adapters.patron import PatronUnitOfWork


@dataclass(frozen=True)
class UpgradePatronTierCommand:
    """Command to upgrade a patron's membership tier."""
    patron_id: str
    new_tier: str


@dataclass(frozen=True)
class UpgradePatronTierResult:
    """Result of upgrading patron tier."""
    id: str
    membership_tier: str
    borrowing_limit: int


class UpgradePatronTierHandler:
    """Handles patron tier upgrades."""

    def __init__(self, uow: PatronUnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: UpgradePatronTierCommand) -> UpgradePatronTierResult:
        async with self.uow:
            patron = await self.uow.patrons.get_by_id(command.patron_id)
            if not patron:
                raise PatronNotFoundException(command.patron_id)

            new_tier = MembershipTier(command.new_tier)
            patron.upgrade_tier(new_tier)

            await self.uow.patrons.update(patron)
            await self.uow.commit()

            self.logger.info(f"Patron tier upgraded: {patron.id.value} -> {new_tier.value}")

            return UpgradePatronTierResult(
                id=patron.id.value,
                membership_tier=patron.membership_tier.value,
                borrowing_limit=patron.membership_tier.borrowing_limit,
            )

"""
Register Patron Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.patron import Patron
from src.domain.patron.value_objects import MembershipTier, PatronName
from src.domain.shared_kernel import EmailAddress

if TYPE_CHECKING:
    from src.domain.shared_kernel import Logger
    from src.infrastructure.adapters.patron import PatronUnitOfWork


@dataclass(frozen=True)
class RegisterPatronCommand:
    """Command to register a new patron."""
    first_name: str
    last_name: str
    email: str
    membership_tier: str = "regular"


@dataclass(frozen=True)
class RegisterPatronResult:
    """Result of registering a patron."""
    id: str
    name: str
    email: str
    membership_tier: str


class RegisterPatronHandler:
    """Handles patron registration."""

    def __init__(self, uow: PatronUnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: RegisterPatronCommand) -> RegisterPatronResult:
        async with self.uow:
            patron = Patron.register(
                name=PatronName(first_name=command.first_name, last_name=command.last_name),
                email=EmailAddress(command.email),
                registered_at=datetime.now(),
                membership_tier=MembershipTier(command.membership_tier),
            )

            await self.uow.patrons.add(patron)
            await self.uow.commit()

            self.logger.info(f"Patron registered: {patron.name.full_name} ({patron.id.value})")

            return RegisterPatronResult(
                id=patron.id.value,
                name=patron.name.full_name,
                email=patron.email.value,
                membership_tier=patron.membership_tier.value,
            )

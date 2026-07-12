"""
Register Patron Command Handler.
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
from src.domain.patron import Patron
from src.domain.patron import PatronEmailAlreadyRegisteredException
from src.domain.patron.value_objects import MembershipTier, PatronName
from src.domain.shared_kernel import EmailAddress

from .patron_snapshot import PatronSnapshot

if TYPE_CHECKING:
    from src.application.ports import IClock, ILogger, IPatronApplicationUnitOfWork


@dataclass(frozen=True)
class RegisterPatronCommand:
    """Command to register a new patron."""
    first_name: str
    last_name: str
    email: str
    membership_tier: str = "regular"
    idempotency_key: str | None = None


@dataclass(frozen=True)
class RegisterPatronResult(PatronSnapshot):
    """Result of registering a patron."""


class RegisterPatronHandler:
    """Handles patron registration."""

    def __init__(
        self, uow: IPatronApplicationUnitOfWork, logger: ILogger, clock: IClock
    ):
        self.uow = uow
        self.logger = logger
        self.clock = clock

    async def handle(self, command: RegisterPatronCommand) -> RegisterPatronResult:
        name = PatronName(first_name=command.first_name, last_name=command.last_name)
        email = EmailAddress(command.email)
        tier = MembershipTier(command.membership_tier.strip().lower())
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        request_hash = command_fingerprint(
            {
                "first_name": name.first_name,
                "last_name": name.last_name,
                "email": email.value,
                "membership_tier": tier.value,
            }
        )
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "patron.register", key.value
                )
                if receipt:
                    return RegisterPatronResult.from_mapping(
                        require_matching_receipt(receipt, request_hash)
                    )

            if await self.uow.patrons.get_by_email(email.value):
                raise PatronEmailAlreadyRegisteredException(email.value)

            patron = Patron.register(
                name=name,
                email=email,
                registered_at=self.clock.now(),
                membership_tier=tier,
            )

            await self.uow.patrons.add(patron)
            result = RegisterPatronResult.from_patron(patron)
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="patron.register",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response=result.__dict__,
                    )
                )
            await self.uow.commit()

            self.logger.info(f"Patron registered: {patron.name.full_name} ({patron.id.value})")

            return result

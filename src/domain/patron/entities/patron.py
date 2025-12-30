"""
Patron Aggregate Root for the Patron bounded context.

A Patron is a library member who can borrow books. This context owns
all information about the patron - their identity, contact info, and
membership details.

The Lending context will reference PatronId when creating loans, but
all patron data stays within this context.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.domain.patron.events.patron_events import (
    PatronRegistered,
    PatronReinstated,
    PatronSuspended,
)
from src.domain.patron.exceptions import (
    InvalidTierUpgradeException,
    PatronAlreadySuspendedException,
    PatronNotSuspendedException,
)
from src.domain.patron.value_objects import MembershipTier, PatronId, PatronName
from src.domain.shared_kernel import AggregateRoot, EmailAddress


@dataclass
class Patron(AggregateRoot):
    """
    A library patron (member).

    Invariants:
    - A patron must have a valid email address
    - A suspended patron cannot borrow books
    - Active loans count must not exceed membership tier limit
    """

    name: PatronName
    email: EmailAddress
    id: PatronId = field(default_factory=PatronId.next_id)
    membership_tier: MembershipTier = MembershipTier.REGULAR
    is_suspended: bool = False
    suspended_reason: Optional[str] = None
    active_loans: int = 0
    registered_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def register(
        cls,
        name: PatronName,
        email: EmailAddress,
        membership_tier: MembershipTier = MembershipTier.REGULAR,
    ) -> "Patron":
        """Factory method to register a new patron."""
        patron = cls(
            name=name,
            email=email,
            membership_tier=membership_tier,
        )
        patron.add_event(
            PatronRegistered(
                patron_id=patron.id.value,
                email=patron.email.value,
                name=patron.name.full_name,
                membership_tier=patron.membership_tier.value,
            )
        )
        return patron

    def can_borrow(self, current_loans: Optional[int] = None) -> bool:
        """Check if patron can borrow another book."""
        if self.is_suspended:
            return False
        # Use internal counter if external not provided
        loans = current_loans if current_loans is not None else self.active_loans
        return loans < self.membership_tier.borrowing_limit

    def suspend(self, reason: str) -> None:
        """Suspend a patron's borrowing privileges."""
        if self.is_suspended:
            raise PatronAlreadySuspendedException(self.id.value)
        self.is_suspended = True
        self.suspended_reason = reason
        self.add_event(
            PatronSuspended(
                patron_id=self.id.value,
                reason=reason,
            )
        )

    def reinstate(self) -> None:
        """Reinstate a suspended patron."""
        if not self.is_suspended:
            raise PatronNotSuspendedException(self.id.value)
        self.is_suspended = False
        self.suspended_reason = None
        self.add_event(PatronReinstated(patron_id=self.id.value))

    def upgrade_tier(self, new_tier: MembershipTier) -> None:
        """Upgrade patron to a higher membership tier."""
        if new_tier.borrowing_limit <= self.membership_tier.borrowing_limit:
            raise InvalidTierUpgradeException(
                self.membership_tier.value, new_tier.value
            )
        self.membership_tier = new_tier
        self.membership_tier = new_tier

    def increment_active_loans(self) -> None:
        self.active_loans += 1

    def decrement_active_loans(self) -> None:
        if self.active_loans > 0:
            self.active_loans -= 1

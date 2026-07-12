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
    InvalidSuspensionReasonException,
    InvalidTierUpgradeException,
    InvalidPatronStateException,
    PatronAlreadySuspendedException,
    PatronNotSuspendedException,
)
from src.domain.patron.value_objects import MembershipTier, PatronId, PatronName
from src.domain.shared_kernel import (
    AggregateRoot,
    EmailAddress,
    aggregate_transition,
    require_utc_datetime,
)


@dataclass
class Patron(AggregateRoot):
    """
    A library patron (member).

    Invariants:
    - A patron must have a valid email address
    - A suspended patron is ineligible for new borrowing workflows
    - Membership tier changes follow the Patron-owned progression
    """

    name: PatronName
    email: EmailAddress
    registered_at: datetime
    id: PatronId = field(default_factory=PatronId.next_id)
    membership_tier: MembershipTier = MembershipTier.REGULAR
    is_suspended: bool = False
    suspended_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, PatronId):
            self.id = PatronId(self.id)
        if not isinstance(self.name, PatronName):
            try:
                self.name = PatronName(*self.name)
            except (TypeError, ValueError) as error:
                raise InvalidPatronStateException("invalid name") from error
        if not isinstance(self.email, EmailAddress):
            self.email = EmailAddress(self.email)
        try:
            if not isinstance(self.membership_tier, MembershipTier):
                self.membership_tier = MembershipTier(self.membership_tier)
        except (TypeError, ValueError) as error:
            raise InvalidPatronStateException("unknown membership tier") from error
        self.registered_at = require_utc_datetime(
            self.registered_at, "registered_at"
        )
        if self.is_suspended:
            reason = " ".join(str(self.suspended_reason or "").split())
            if not reason or len(reason) > 500:
                raise InvalidPatronStateException(
                    "suspended patron requires a bounded reason"
                )
            self.suspended_reason = reason
        elif self.suspended_reason is not None:
            raise InvalidPatronStateException(
                "active patron cannot retain a suspension reason"
            )
        super().__post_init__()

    @classmethod
    def register(
        cls,
        name: PatronName,
        email: EmailAddress,
        registered_at: datetime,
        membership_tier: MembershipTier = MembershipTier.REGULAR,
    ) -> "Patron":
        """Factory method to register a new patron."""
        patron = cls(
            name=name,
            email=email,
            registered_at=registered_at,
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

    @aggregate_transition
    def suspend(self, reason: str) -> None:
        """Suspend a patron's borrowing privileges."""
        if self.is_suspended:
            raise PatronAlreadySuspendedException(self.id.value)
        reason = " ".join(str(reason).split())
        if not reason or len(reason) > 500:
            raise InvalidSuspensionReasonException()
        self.is_suspended = True
        self.suspended_reason = reason
        self.add_event(
            PatronSuspended(
                patron_id=self.id.value,
                reason=reason,
            )
        )

    @aggregate_transition
    def reinstate(self) -> None:
        """Reinstate a suspended patron."""
        if not self.is_suspended:
            raise PatronNotSuspendedException(self.id.value)
        self.is_suspended = False
        self.suspended_reason = None
        self.add_event(PatronReinstated(patron_id=self.id.value))

    @aggregate_transition
    def upgrade_tier(self, new_tier: MembershipTier) -> None:
        """Upgrade patron to a higher membership tier."""
        progression = {
            MembershipTier.REGULAR: 0,
            MembershipTier.PREMIUM: 1,
            MembershipTier.RESEARCHER: 2,
        }
        if progression[new_tier] <= progression[self.membership_tier]:
            raise InvalidTierUpgradeException(
                self.membership_tier.value, new_tier.value
            )
        self.membership_tier = new_tier

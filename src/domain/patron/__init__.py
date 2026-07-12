"""
Patron Bounded Context

This context manages library patrons (members) - the people who borrow books.
It handles:

- Member registration and profiles
- Membership classification and suspension eligibility
- Member contact information

Key Aggregates:
- Patron: A library member who can borrow books

Ubiquitous Language:
- Patron: A registered library member
- PatronId: Unique identifier for a patron
- MembershipTier: Level of membership (REGULAR, PREMIUM)

Context Relationships:
- Upstream to Lending: Provides identity, membership tier, and eligibility
- Lending owns borrowing limits and loan durations for those membership facts
- Relationship Type: Customer-Supplier (Lending is the customer)
"""
from .entities.patron import Patron
from .events.patron_events import PatronRegistered, PatronReinstated, PatronSuspended
from .exceptions import (
    InvalidPatronIdException,
    InvalidPatronNameException,
    InvalidPatronStateException,
    InvalidSuspensionReasonException,
    InvalidTierUpgradeException,
    PatronAlreadySuspendedException,
    PatronNotSuspendedException,
    PatronEmailAlreadyRegisteredException,
    PatronNotFoundException,
)
from .interfaces import IPatronCommandRepository
from .value_objects.patron_info import MembershipTier, PatronId, PatronName

__all__ = [
    "Patron",
    "PatronId",
    "PatronName",
    "MembershipTier",
    "PatronRegistered",
    "PatronSuspended",
    "PatronReinstated",
    "IPatronCommandRepository",
    "InvalidPatronIdException",
    "InvalidPatronNameException",
    "InvalidPatronStateException",
    "InvalidTierUpgradeException",
    "PatronAlreadySuspendedException",
    "PatronNotSuspendedException",
    "InvalidSuspensionReasonException",
    "PatronEmailAlreadyRegisteredException",
    "PatronNotFoundException",
]

"""
Patron Bounded Context

This context manages library patrons (members) - the people who borrow books.
It handles:

- Member registration and profiles
- Membership tiers and privileges
- Borrowing limits and holds
- Member contact information

Key Aggregates:
- Patron: A library member who can borrow books

Ubiquitous Language:
- Patron: A registered library member
- PatronId: Unique identifier for a patron
- MembershipTier: Level of membership (REGULAR, PREMIUM)
- BorrowingLimit: Maximum books a patron can borrow

Context Relationships:
- Upstream to Lending: Provides patron identity that Lending uses for loans
- Relationship Type: Customer-Supplier (Lending is the customer)
"""
from .entities.patron import Patron
from .events.patron_events import PatronRegistered, PatronReinstated, PatronSuspended
from .exceptions import (
    InvalidPatronIdException,
    InvalidPatronNameException,
    InvalidTierUpgradeException,
    PatronAlreadySuspendedException,
    PatronNotSuspendedException,
)
from .interfaces import IPatronCommandRepository, IPatronUnitOfWork
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
    "IPatronUnitOfWork",
    "InvalidPatronIdException",
    "InvalidPatronNameException",
    "InvalidTierUpgradeException",
    "PatronAlreadySuspendedException",
    "PatronNotSuspendedException",
]

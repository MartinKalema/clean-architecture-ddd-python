"""
Domain events for the Patron bounded context.
"""
from dataclasses import dataclass

from src.domain.shared_kernel import DomainEvent


@dataclass(frozen=True)
class PatronRegistered(DomainEvent):
    """Published when a new patron registers with the library."""

    patron_id: str
    email: str
    name: str
    membership_tier: str


@dataclass(frozen=True)
class PatronSuspended(DomainEvent):
    """Published when a patron's borrowing privileges are suspended."""

    patron_id: str
    reason: str


@dataclass(frozen=True)
class PatronReinstated(DomainEvent):
    """Published when a suspended patron is reinstated."""

    patron_id: str

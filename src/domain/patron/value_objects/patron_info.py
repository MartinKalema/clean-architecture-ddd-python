"""
Value Objects for the Patron bounded context.
"""
import uuid
from dataclasses import dataclass
from enum import Enum

from src.domain.patron.exceptions import (
    InvalidPatronIdException,
    InvalidPatronNameException,
)


@dataclass(frozen=True)
class PatronId:
    """Unique identifier for a library patron."""

    value: str

    def __post_init__(self):
        if not self.value:
            raise InvalidPatronIdException()

    @classmethod
    def next_id(cls) -> "PatronId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class PatronName:
    """Full name of a patron."""

    first_name: str
    last_name: str

    def __post_init__(self):
        if not self.first_name:
            raise InvalidPatronNameException("First name")
        if not self.last_name:
            raise InvalidPatronNameException("Last name")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class MembershipTier(Enum):
    """
    Membership tiers determine borrowing privileges.

    Different tiers have different:
    - Borrowing limits
    - Loan durations
    - Hold limits
    """

    REGULAR = "regular"
    PREMIUM = "premium"
    RESEARCHER = "researcher"

    @property
    def borrowing_limit(self) -> int:
        """Maximum number of books that can be borrowed simultaneously."""
        limits = {
            MembershipTier.REGULAR: 5,
            MembershipTier.PREMIUM: 10,
            MembershipTier.RESEARCHER: 20,
        }
        return limits[self]

    @property
    def loan_duration_days(self) -> int:
        """Number of days a book can be borrowed."""
        durations = {
            MembershipTier.REGULAR: 14,
            MembershipTier.PREMIUM: 21,
            MembershipTier.RESEARCHER: 30,
        }
        return durations[self]

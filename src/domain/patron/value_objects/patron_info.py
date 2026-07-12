"""
Value Objects for the Patron bounded context.
"""
import uuid
from dataclasses import dataclass
from enum import Enum
import re

from src.domain.patron.exceptions import (
    InvalidPatronIdException,
    InvalidPatronNameException,
)


@dataclass(frozen=True)
class PatronId:
    """Unique identifier for a library patron."""

    value: str

    def __post_init__(self):
        value = str(self.value).strip()
        if not value:
            raise InvalidPatronIdException()
        if len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
            raise InvalidPatronIdException()
        try:
            value = str(uuid.UUID(value))
        except ValueError:
            pass
        object.__setattr__(self, "value", value)

    @classmethod
    def next_id(cls) -> "PatronId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class PatronName:
    """Full name of a patron."""

    first_name: str
    last_name: str

    def __post_init__(self):
        first_name = " ".join(str(self.first_name).split())
        last_name = " ".join(str(self.last_name).split())
        if not first_name:
            raise InvalidPatronNameException("First name")
        if not last_name:
            raise InvalidPatronNameException("Last name")
        if len(first_name) > 100:
            raise InvalidPatronNameException("First name", "is too long")
        if len(last_name) > 100:
            raise InvalidPatronNameException("Last name", "is too long")
        object.__setattr__(self, "first_name", first_name)
        object.__setattr__(self, "last_name", last_name)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class MembershipTier(Enum):
    """
    Patron-owned membership classification.

    Borrowing capacity and loan duration are Lending policy.  Keeping those
    values out of this upstream context prevents a Patron model change from
    silently changing Lending invariants.
    """

    REGULAR = "regular"
    PREMIUM = "premium"
    RESEARCHER = "researcher"

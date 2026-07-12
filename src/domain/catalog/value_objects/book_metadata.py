"""
Value Objects for the Catalog bounded context.
"""
import uuid
from dataclasses import dataclass
from enum import Enum
import re

from src.domain.shared_kernel.exceptions import ValidationException


class BookStatus(str, Enum):
    """
    Lifecycle of a catalog book.

    RESERVED is a semantic lock: the borrow has committed but the loan in
    the Lending context has not yet been confirmed. The book is withheld
    from other borrowers, but the state is tentative — it either advances
    to BORROWED (loan created) or falls back to AVAILABLE (compensation
    or reservation expiry).
    """

    AVAILABLE = "available"
    RESERVED = "reserved"
    BORROWED = "borrowed"


@dataclass(frozen=True)
class BookId:
    """Unique identifier for a book in the catalog."""
    value: str

    def __post_init__(self):
        value = str(self.value).strip()
        if not value:
            raise ValidationException("BookId cannot be empty")
        if len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
            raise ValidationException("BookId has an invalid format")
        try:
            value = str(uuid.UUID(value))
        except ValueError:
            # External catalog IDs may be bounded opaque identifiers rather
            # than UUIDs.
            pass
        object.__setattr__(self, "value", value)

    @classmethod
    def next_id(cls) -> "BookId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class ReservationId:
    """
    Globally unique correlation token for one borrow attempt.

    A book can be reserved many times over its lifetime.  The book id alone
    therefore cannot identify which attempt an asynchronous confirmation or
    compensation belongs to.  ReservationId is the stable identity of that
    attempt; ``reservation_generation`` on the aggregate is its fencing token.
    """

    value: str

    def __post_init__(self) -> None:
        try:
            canonical = str(uuid.UUID(str(self.value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValidationException("ReservationId must be a valid UUID") from exc
        object.__setattr__(self, "value", canonical)

    @classmethod
    def next_id(cls) -> "ReservationId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class Title:
    """The title of a book."""
    value: str

    def __post_init__(self):
        value = " ".join(str(self.value).split())
        if not value:
            raise ValidationException("Title cannot be empty")
        if len(value) > 100:
            raise ValidationException("Title cannot be longer than 100 characters")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class Author:
    """The author of a book."""
    value: str

    def __post_init__(self):
        value = " ".join(str(self.value).split())
        if not value:
            raise ValidationException("Author cannot be empty")
        if len(value) > 200:
            raise ValidationException("Author cannot be longer than 200 characters")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class ISBN:
    """International Standard Book Number (optional)."""
    value: str

    def __post_init__(self):
        if self.value:
            clean = self.value.replace("-", "").replace(" ", "").upper()
            if len(clean) not in (10, 13):
                raise ValidationException("ISBN must be 10 or 13 digits")
            if not (clean.isdigit() or (len(clean) == 10 and clean[:-1].isdigit() and clean[-1] == "X")):
                raise ValidationException("ISBN must contain only digits")
            if not self._has_valid_checksum(clean):
                raise ValidationException("ISBN checksum is invalid")
            object.__setattr__(self, "value", clean)

    @staticmethod
    def _has_valid_checksum(value: str) -> bool:
        if len(value) == 10:
            digits = [10 if char == "X" else int(char) for char in value]
            return sum((10 - index) * digit for index, digit in enumerate(digits)) % 11 == 0
        return (
            sum(
                int(char) * (1 if index % 2 == 0 else 3)
                for index, char in enumerate(value[:12])
            )
            + int(value[12])
        ) % 10 == 0

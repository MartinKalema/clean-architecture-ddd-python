"""
Value Objects for the Lending bounded context.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re

from src.domain.lending.exceptions import (
    InvalidLoanDurationException,
    InvalidLoanExtensionException,
    InvalidLoanIdException,
    InvalidReservationIdException,
)
from src.domain.shared_kernel import require_utc_datetime


@dataclass(frozen=True)
class LoanId:
    """Unique identifier for a loan."""

    value: str

    def __post_init__(self):
        value = str(self.value).strip()
        if not value:
            raise InvalidLoanIdException()
        if len(value) > 64 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
            raise InvalidLoanIdException()
        try:
            value = str(uuid.UUID(value))
        except ValueError:
            pass
        object.__setattr__(self, "value", value)

    @classmethod
    def next_id(cls) -> "LoanId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class ReservationId:
    """Lending's local representation of a Catalog reservation identity."""

    value: str

    def __post_init__(self) -> None:
        try:
            canonical = str(uuid.UUID(str(self.value)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidReservationIdException() from exc
        object.__setattr__(self, "value", canonical)


@dataclass(frozen=True)
class DueDate:
    """
    When a borrowed book must be returned.

    This is a value object because the concept of "due date" has
    meaning beyond just a datetime - it has business rules attached.
    """

    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            require_utc_datetime(self.value, "due_date"),
        )

    @classmethod
    def from_loan_duration(cls, loan_date: datetime, days: int) -> "DueDate":
        """Create a due date from a loan date and duration."""
        if days <= 0:
            raise InvalidLoanDurationException(days)
        loan_date = require_utc_datetime(loan_date, "borrowed_at")
        return cls(loan_date + timedelta(days=days))

    def is_overdue_as_of(self, current_time: datetime) -> bool:
        """Check if the due date has passed as of the given time."""
        return require_utc_datetime(current_time, "current_time") > self.value

    def days_until_due_as_of(self, current_time: datetime) -> int:
        """Days remaining until due (negative if overdue) as of the given time."""
        delta = self.value - require_utc_datetime(current_time, "current_time")
        return delta.days

    def extend(self, days: int) -> "DueDate":
        """Extend the due date by a number of days."""
        if days <= 0:
            raise InvalidLoanExtensionException(days)
        return DueDate(self.value + timedelta(days=days))


class LoanStatus(Enum):
    """Status of a loan throughout its lifecycle."""

    ACTIVE = "active"
    RETURNED = "returned"
    OVERDUE = "overdue"
    LOST = "lost"
    CANCELLED = "cancelled"

"""
Value Objects for the Lending bounded context.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from src.domain.lending.exceptions import InvalidLoanIdException


@dataclass(frozen=True)
class LoanId:
    """Unique identifier for a loan."""

    value: str

    def __post_init__(self):
        if not self.value:
            raise InvalidLoanIdException()

    @classmethod
    def next_id(cls) -> "LoanId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class DueDate:
    """
    When a borrowed book must be returned.

    This is a value object because the concept of "due date" has
    meaning beyond just a datetime - it has business rules attached.
    """

    value: datetime

    @classmethod
    def from_loan_duration(cls, loan_date: datetime, days: int) -> "DueDate":
        """Create a due date from a loan date and duration."""
        return cls(loan_date + timedelta(days=days))

    def is_overdue_as_of(self, current_time: datetime) -> bool:
        """Check if the due date has passed as of the given time."""
        return current_time > self.value

    def days_until_due_as_of(self, current_time: datetime) -> int:
        """Days remaining until due (negative if overdue) as of the given time."""
        delta = self.value - current_time
        return delta.days

    def extend(self, days: int) -> "DueDate":
        """Extend the due date by a number of days."""
        return DueDate(self.value + timedelta(days=days))


class LoanStatus(Enum):
    """Status of a loan throughout its lifecycle."""

    ACTIVE = "active"
    RETURNED = "returned"
    OVERDUE = "overdue"
    LOST = "lost"

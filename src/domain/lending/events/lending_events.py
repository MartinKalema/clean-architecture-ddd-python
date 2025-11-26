"""
Domain events for the Lending bounded context.

These events represent significant things that happened in the lending domain.
Other contexts (like Notification) can subscribe to these events.
"""
from dataclasses import dataclass
from datetime import datetime

from src.domain.shared_kernel import DomainEvent


@dataclass(frozen=True)
class BookBorrowed(DomainEvent):
    """
    Published when a book is borrowed.

    This is an integration event that Notification context subscribes to
    in order to send confirmation emails.
    """

    loan_id: str
    patron_id: str
    patron_email: str
    book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime


@dataclass(frozen=True)
class BookReturned(DomainEvent):
    """Published when a book is returned."""

    loan_id: str
    patron_id: str
    book_id: str
    returned_at: datetime
    was_overdue: bool


@dataclass(frozen=True)
class BookOverdue(DomainEvent):
    """
    Published when a loan becomes overdue.

    Notification context subscribes to this to send reminder emails.
    """

    loan_id: str
    patron_id: str
    patron_email: str
    book_id: str
    book_title: str
    due_date: datetime
    days_overdue: int


@dataclass(frozen=True)
class LoanExtended(DomainEvent):
    """Published when a loan is extended."""

    loan_id: str
    patron_id: str
    book_id: str
    old_due_date: datetime
    new_due_date: datetime

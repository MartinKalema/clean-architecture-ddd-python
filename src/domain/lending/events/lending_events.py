"""
Domain events for the Lending bounded context.

These events represent significant things that happened in the lending domain.
Other contexts (like Notification) can subscribe to these events.
"""
from dataclasses import dataclass
from datetime import datetime

from src.domain.shared_kernel import DomainEvent


@dataclass(frozen=True)
class LoanCreated(DomainEvent):
    """
    Published when a loan is created.

    Catalog consumes this tentative fact to confirm the exact reservation.
    Notifications wait for ``CatalogBookBorrowed`` so a loan that must be
    compensated can never produce a false confirmation email.
    """

    loan_id: str
    reservation_id: str
    reservation_generation: int
    patron_id: str
    patron_email: str
    book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime


@dataclass(frozen=True)
class LoanCompleted(DomainEvent):
    """Published when a loan is completed (book returned)."""

    loan_id: str
    reservation_id: str
    reservation_generation: int
    patron_id: str
    book_id: str
    returned_at: datetime
    was_overdue: bool


@dataclass(frozen=True)
class LoanCancelled(DomainEvent):
    """
    Published when a tentative loan cannot be confirmed by Catalog.

    Cancellation is compensation, not a return: it frees the outstanding-loan
    uniqueness slot without claiming the patron possessed and returned a book.
    """

    loan_id: str
    reservation_id: str
    reservation_generation: int
    patron_id: str
    book_id: str
    reason: str


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

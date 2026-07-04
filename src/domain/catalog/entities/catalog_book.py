"""
Book Aggregate Root for the Catalog bounded context.

The book's availability is a state machine, not a boolean:

    AVAILABLE --reserve()--> RESERVED --confirm_borrow()--> BORROWED
                                 |                              |
                             release()                    return_book()
                                 v                              v
                             AVAILABLE                      AVAILABLE

RESERVED is a semantic lock for the borrow saga: it withholds the book
from other borrowers while the Lending context creates the loan, without
pretending the borrow is final. Only one saga can hold a book at a time —
reserve() rejects anything not AVAILABLE.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from src.domain.catalog.events import (
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
    CatalogBookReturned,
)
from src.domain.catalog.exceptions import (
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
    BookNotReservedException,
    BorrowerEmailRequiredException,
)
from src.domain.catalog.value_objects import Author, BookId, BookStatus, Title
from src.domain.shared_kernel import AggregateRoot

LOAN_PERIOD_DAYS = 14


@dataclass
class Book(AggregateRoot):
    """A book in the library catalog."""
    title: Title
    author: Author
    id: BookId = field(default_factory=BookId.next_id)
    status: BookStatus = BookStatus.AVAILABLE
    reserved_at: Optional[datetime] = None
    borrowed_at: Optional[datetime] = None
    return_due_date: Optional[datetime] = None

    @property
    def is_borrowed(self) -> bool:
        """Whether the book is unavailable to other borrowers."""
        return self.status != BookStatus.AVAILABLE

    def reserve(self, borrower_email: str, reserved_at: datetime):
        """
        Reserve the book for a borrower (tentative first step of the
        borrow saga).
        """
        if self.status != BookStatus.AVAILABLE:
            raise BookAlreadyBorrowedException(self.id.value)

        if not borrower_email or not borrower_email.strip():
            raise BorrowerEmailRequiredException()

        self.status = BookStatus.RESERVED
        self.reserved_at = reserved_at
        self.borrowed_at = reserved_at
        self.return_due_date = reserved_at + timedelta(days=LOAN_PERIOD_DAYS)

        self.add_event(CatalogBookReserved(
            book_id=self.id.value,
            title=self.title.value,
            reserved_at=reserved_at,
            return_due_date=self.return_due_date,
            borrower_email=borrower_email
        ))

    def confirm_borrow(self, borrower_email: str):
        """Confirm the reservation into a final borrow (loan created)."""
        if self.status != BookStatus.RESERVED:
            raise BookNotReservedException(self.id.value, self.status.value)

        self.status = BookStatus.BORROWED
        self.reserved_at = None

        self.add_event(CatalogBookBorrowed(
            book_id=self.id.value,
            title=self.title.value,
            borrowed_at=self.borrowed_at,
            return_due_date=self.return_due_date,
            borrower_email=borrower_email
        ))

    def release(self, reason: str):
        """Release the reservation without a borrow (compensation/expiry)."""
        if self.status != BookStatus.RESERVED:
            raise BookNotReservedException(self.id.value, self.status.value)

        self.status = BookStatus.AVAILABLE
        self.reserved_at = None
        self.borrowed_at = None
        self.return_due_date = None

        self.add_event(CatalogBookReleased(book_id=self.id.value, reason=reason))

    def return_book(self):
        """Return the book after a confirmed borrow."""
        if self.status != BookStatus.BORROWED:
            raise BookNotBorrowedException(self.id.value)

        self.status = BookStatus.AVAILABLE
        self.borrowed_at = None
        self.return_due_date = None

        self.add_event(CatalogBookReturned(book_id=self.id.value))

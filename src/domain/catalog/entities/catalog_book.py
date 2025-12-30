"""
Book Aggregate Root for the Catalog bounded context.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from src.domain.catalog.events import CatalogBookBorrowed, CatalogBookReturned
from src.domain.catalog.exceptions import (
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
    BorrowerEmailRequiredException,
)
from src.domain.catalog.value_objects import Author, BookId, Title
from src.domain.shared_kernel import AggregateRoot


@dataclass
class Book(AggregateRoot):
    """A book in the library catalog."""
    title: Title
    author: Author
    id: BookId = field(default_factory=BookId.next_id)
    is_borrowed: bool = False
    borrowed_at: Optional[datetime] = None
    return_due_date: Optional[datetime] = None

    def borrow(self, borrower_email: str, borrowed_at: datetime):
        """Borrow the book."""
        if self.is_borrowed:
            raise BookAlreadyBorrowedException(self.id.value)

        if not borrower_email or not borrower_email.strip():
            raise BorrowerEmailRequiredException()

        self.is_borrowed = True
        self.borrowed_at = borrowed_at
        self.return_due_date = self.borrowed_at + timedelta(days=14)

        self.add_event(CatalogBookBorrowed(
            book_id=self.id.value,
            title=self.title.value,
            borrowed_at=self.borrowed_at,
            return_due_date=self.return_due_date,
            borrower_email=borrower_email
        ))

    def return_book(self):
        """Return the book."""
        if not self.is_borrowed:
            raise BookNotBorrowedException(self.id.value)
        self.is_borrowed = False
        self.add_event(CatalogBookReturned(book_id=self.id.value))

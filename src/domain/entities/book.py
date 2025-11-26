from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional
from src.domain.value_objects.book_value_objects import BookId, Title, Author
from src.domain.exceptions.book_exceptions import BookAlreadyBorrowedException, BookNotBorrowedException
from src.domain.events.book_events import DomainEvent, BookBorrowed, BookReturned

@dataclass
class AggregateRoot:
    _domain_events: List[DomainEvent] = field(default_factory=list, init=False, repr=False)

    def add_event(self, event: DomainEvent):
        self._domain_events.append(event)

    def clear_events(self):
        self._domain_events.clear()

    def get_domain_events(self) -> List[DomainEvent]:
        return list(self._domain_events)

@dataclass
class Book(AggregateRoot):
    title: Title
    author: Author
    id: BookId = field(default_factory=BookId.next_id)
    is_borrowed: bool = False
    borrowed_at: Optional[datetime] = None
    return_due_date: Optional[datetime] = None

    def borrow(self, borrower_email: str):
        if self.is_borrowed:
            raise BookAlreadyBorrowedException(self.id.value)

        if not borrower_email or not borrower_email.strip():
            raise ValueError("Borrower email is required")

        self.is_borrowed = True
        self.borrowed_at = datetime.now()
        self.return_due_date = self.borrowed_at + timedelta(days=14)

        self.add_event(BookBorrowed(
            book_id=self.id.value,
            title=self.title.value,
            borrowed_at=self.borrowed_at,
            return_due_date=self.return_due_date,
            borrower_email=borrower_email
        ))

    def return_book(self):
        if not self.is_borrowed:
            raise BookNotBorrowedException(self.id.value)
        self.is_borrowed = False
        self.add_event(BookReturned(book_id=self.id.value))

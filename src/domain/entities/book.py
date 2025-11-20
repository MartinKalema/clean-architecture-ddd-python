from dataclasses import dataclass, field
from typing import List
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

    def borrow(self):
        if self.is_borrowed:
            raise BookAlreadyBorrowedException(self.id.value)
        self.is_borrowed = True
        self.add_event(BookBorrowed(book_id=self.id.value))

    def return_book(self):
        if not self.is_borrowed:
            raise BookNotBorrowedException(self.id.value)
        self.is_borrowed = False
        self.add_event(BookReturned(book_id=self.id.value))

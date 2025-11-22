from dataclasses import dataclass
from src.domain.events.domain_event import DomainEvent

from datetime import datetime

@dataclass(frozen=True)
class BookBorrowed(DomainEvent):
    book_id: str
    title: str
    borrowed_at: datetime
    return_due_date: datetime
    borrower_email: str

@dataclass(frozen=True)
class BookReturned(DomainEvent):
    book_id: str

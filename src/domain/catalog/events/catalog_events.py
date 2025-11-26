"""
Domain events for the Catalog bounded context.
"""
from dataclasses import dataclass
from datetime import datetime

from src.domain.shared_kernel import DomainEvent


@dataclass(frozen=True)
class BookAddedToCatalog(DomainEvent):
    """Published when a new book is added to the catalog."""
    book_id: str
    title: str
    author: str


@dataclass(frozen=True)
class BookRemovedFromCatalog(DomainEvent):
    """Published when a book is removed from the catalog."""
    book_id: str


@dataclass(frozen=True)
class BookBorrowed(DomainEvent):
    """Published when a book is borrowed."""
    book_id: str
    title: str
    borrowed_at: datetime
    return_due_date: datetime
    borrower_email: str


@dataclass(frozen=True)
class BookReturned(DomainEvent):
    """Published when a book is returned."""
    book_id: str

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
class CatalogBookReserved(DomainEvent):
    """
    Published when a book is reserved for a borrower.

    A reservation is the tentative first step of the borrow saga: the
    Lending context reacts by creating the loan, after which the
    reservation is confirmed into a borrow (or released on failure).
    """
    book_id: str
    title: str
    reserved_at: datetime
    return_due_date: datetime
    borrower_email: str


@dataclass(frozen=True)
class CatalogBookBorrowed(DomainEvent):
    """Published when a reservation is confirmed into a final borrow."""
    book_id: str
    title: str
    borrowed_at: datetime
    return_due_date: datetime
    borrower_email: str


@dataclass(frozen=True)
class CatalogBookReleased(DomainEvent):
    """Published when a reservation is released without becoming a borrow."""
    book_id: str
    reason: str


@dataclass(frozen=True)
class CatalogBookReturned(DomainEvent):
    """Published when a book is returned to the catalog."""
    book_id: str

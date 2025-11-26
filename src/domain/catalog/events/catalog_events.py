"""
Domain events for the Catalog bounded context.

These events are part of the Published Language between Catalog and other
contexts. When Catalog publishes these events, other contexts (like Lending)
can react to them.
"""
from dataclasses import dataclass

from src.domain.shared_kernel import DomainEvent


@dataclass(frozen=True)
class BookAddedToCatalog(DomainEvent):
    """
    Published when a new book is added to the catalog.

    Downstream contexts (e.g., Lending) can subscribe to this event
    to create their own representation of the book.
    """

    book_id: str
    title: str
    author: str


@dataclass(frozen=True)
class BookRemovedFromCatalog(DomainEvent):
    """
    Published when a book is removed from the catalog.

    Downstream contexts should handle this by marking their
    references as unavailable.
    """

    book_id: str

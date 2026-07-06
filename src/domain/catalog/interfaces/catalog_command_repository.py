"""
Command Repository interface for Book aggregate.
"""
from datetime import datetime
from typing import List, Optional, Protocol

from src.domain.catalog.entities import Book


class IBookCommandRepository(Protocol):
    """Command repository interface for Book aggregates."""

    async def add(self, book: Book) -> Book:
        """Add a new book to the catalog."""
        ...

    async def get_by_id(self, book_id: str) -> Optional[Book]:
        """Find a book by its ID."""
        ...

    async def find_expired_reservations(self, cutoff: datetime) -> List[Book]:
        """Find books whose reservation started before the cutoff."""
        ...

    async def get_all(self) -> List[Book]:
        """Get all books in the catalog."""
        ...

    async def update(self, book: Book) -> None:
        """Update a book."""
        ...

    async def remove(self, book_id: str) -> None:
        """Remove a book from the catalog."""
        ...

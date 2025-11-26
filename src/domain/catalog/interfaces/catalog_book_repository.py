"""
Repository interface for the Catalog bounded context.
"""
from typing import List, Optional, Protocol

from src.domain.catalog.entities import Book


class BookRepository(Protocol):
    """Repository for Book aggregates."""

    async def add(self, book: Book) -> Book:
        """Add a new book to the catalog."""
        ...

    async def get_by_id(self, book_id: str) -> Optional[Book]:
        """Find a book by its ID."""
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

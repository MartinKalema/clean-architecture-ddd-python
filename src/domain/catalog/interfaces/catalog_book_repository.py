"""
Repository interface for the Catalog bounded context.
"""
from typing import List, Optional, Protocol

from src.domain.catalog.entities import CatalogBook


class CatalogBookRepository(Protocol):
    """Repository for CatalogBook aggregates."""

    async def add(self, book: CatalogBook) -> CatalogBook:
        """Add a new book to the catalog."""
        ...

    async def get_by_id(self, book_id: str) -> Optional[CatalogBook]:
        """Find a book by its ID."""
        ...

    async def get_all(self) -> List[CatalogBook]:
        """Get all books in the catalog."""
        ...

    async def update(self, book: CatalogBook) -> None:
        """Update a book's metadata."""
        ...

    async def remove(self, book_id: str) -> None:
        """Remove a book from the catalog."""
        ...

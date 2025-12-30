"""
Anti-Corruption Layer for the Catalog bounded context.

This ACL translates between the Catalog context's model and the
Lending context's needs. The Lending context doesn't need all the
rich book metadata - it only needs what's relevant for lending.
"""
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class BookReference:
    """
    The Lending context's simplified view of a book.

    This is what we need from the Catalog context, translated into
    our own terms. We don't care about ISBN, description, etc.
    """

    catalog_book_id: str
    title: str
    author: str


class CatalogService(Protocol):
    """
    Service interface for the Catalog context.

    This protocol defines what Lending needs from Catalog.
    """

    async def get_book_reference(self, catalog_book_id: str) -> Optional[BookReference]:
        """
        Get book information needed for lending.

        Args:
            catalog_book_id: The book's ID in the Catalog context

        Returns:
            BookReference with the data we need, or None if not found
        """
        ...

    async def book_exists(self, catalog_book_id: str) -> bool:
        """Check if a book exists in the catalog."""
        ...

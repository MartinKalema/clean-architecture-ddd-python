"""
Repository interface for LoanableBook aggregates.
"""
from typing import Optional, Protocol

from src.domain.lending.entities import LoanableBook


class LoanableBookRepository(Protocol):
    """Repository for LoanableBook aggregates."""

    async def add(self, book: LoanableBook) -> LoanableBook:
        """Add a new loanable book (when Catalog adds a book)."""
        ...

    async def get_by_catalog_id(self, catalog_book_id: str) -> Optional[LoanableBook]:
        """Find a loanable book by its catalog ID."""
        ...

    async def update(self, book: LoanableBook) -> None:
        """Update a loanable book's availability."""
        ...

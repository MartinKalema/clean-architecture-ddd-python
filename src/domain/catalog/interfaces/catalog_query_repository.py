"""
Catalog Query Repository Interface - CQRS Read Side.

This interface defines read operations separate from the write model.
Implementations can be optimized for queries (denormalized, cached, etc.).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.application.query_handlers import BookReadModel


@runtime_checkable
class IBookQueryRepository(Protocol):
    """
    Query repository interface for Book (CQRS read side).

    This is separate from the command repository to allow
    independent optimization of reads vs writes.
    """

    async def find_by_id(self, book_id: str) -> Optional[BookReadModel]:
        """Find a book by its ID."""
        ...

    async def find_all(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
        author_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BookReadModel]:
        """Find books with optional filters."""
        ...

    async def count(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
    ) -> int:
        """Count books matching criteria."""
        ...

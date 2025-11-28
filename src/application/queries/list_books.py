"""
List Books Query - CQRS Query Side.

Queries are read-only operations that return data from the read model.
They never modify state and can be optimized independently from writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.domain.catalog import BookQueryRepository
    from src.domain.shared_kernel import Logger


@dataclass(frozen=True)
class BookReadModel:
    """
    Read-optimized book representation.

    This is a denormalized view optimized for display,
    separate from the write model (domain aggregate).
    """
    id: str
    title: str
    author: str
    is_borrowed: bool
    borrowed_at: Optional[datetime] = None
    return_due_date: Optional[datetime] = None


@dataclass(frozen=True)
class ListBooksQuery:
    """
    Query to list books.

    Can include filters for optimized read queries.
    """
    only_available: bool = False
    only_borrowed: bool = False
    author_contains: Optional[str] = None
    title_contains: Optional[str] = None
    limit: int = 100
    offset: int = 0


class ListBooksHandler:
    """
    Handles the ListBooksQuery.

    Reads from the optimized read model, not the write model.
    This allows for:
    - Denormalized data for fast queries
    - Caching without affecting writes
    - Different storage optimized for reads
    """

    def __init__(self, query_repository: BookQueryRepository, logger: Logger):
        self.query_repository = query_repository
        self.logger = logger

    async def handle(self, query: ListBooksQuery) -> List[BookReadModel]:
        """Execute the query to list books."""
        books = await self.query_repository.find_all(
            only_available=query.only_available,
            only_borrowed=query.only_borrowed,
            author_contains=query.author_contains,
            title_contains=query.title_contains,
            limit=query.limit,
            offset=query.offset,
        )

        self.logger.info(f"Listed {len(books)} books (query side)")
        return books

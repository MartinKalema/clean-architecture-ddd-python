"""
Get Book Query - CQRS Query Side.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.catalog import BookNotFoundException

from .list_books import BookReadModel

if TYPE_CHECKING:
    from src.domain.catalog import BookQueryRepository
    from src.domain.shared_kernel import Logger


@dataclass(frozen=True)
class GetBookQuery:
    """Query to get a single book by ID."""
    book_id: str


class GetBookHandler:
    """
    Handles the GetBookQuery.

    Reads from the optimized read model.
    """

    def __init__(self, query_repository: BookQueryRepository, logger: Logger):
        self.query_repository = query_repository
        self.logger = logger

    async def handle(self, query: GetBookQuery) -> BookReadModel:
        """Execute the query to get a book."""
        book = await self.query_repository.find_by_id(query.book_id)

        if not book:
            self.logger.warning(f"Book not found: {query.book_id}")
            raise BookNotFoundException(query.book_id)

        self.logger.info(f"Retrieved book: {book.title} (query side)")
        return book

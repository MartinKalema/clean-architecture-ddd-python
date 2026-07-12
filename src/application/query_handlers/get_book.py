"""
Get Book Query - CQRS Query Side.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.catalog import BookNotFoundException

from .read_models import BookReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import IBookQueryRepository
    from src.application.ports import ICache, ILogger


@dataclass(frozen=True)
class GetBookQuery:
    """Query to get a single book by ID."""
    book_id: str


class GetBookHandler:
    """
    Handles the GetBookQuery.

    Reads from the optimized read model with caching.
    """

    CACHE_PREFIX = "book"

    def __init__(
        self,
        query_repository: IBookQueryRepository,
        cache: ICache,
        logger: ILogger,
    ):
        self.query_repository = query_repository
        self.cache = cache
        self.logger = logger

    async def handle(self, query: GetBookQuery) -> BookReadModel:
        """Execute the query to get a book."""
        cache_key = self.cache.build_key(self.CACHE_PREFIX, query.book_id)

        async def load() -> dict:
            book = await self.query_repository.find_by_id(query.book_id)
            if not book:
                self.logger.warning(f"Book not found: {query.book_id}")
                raise BookNotFoundException(query.book_id)
            return book.__dict__

        cached = await self.cache.get_or_set(cache_key, load)
        book = BookReadModel.from_mapping(cached)
        self.logger.info(f"Retrieved book: {book.title} (query side)")
        return book

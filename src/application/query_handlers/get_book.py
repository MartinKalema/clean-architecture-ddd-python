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
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.adapters.cache import CacheAdapter


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
        query_repository: BookQueryRepository,
        cache: CacheAdapter,
        logger: ILogger,
    ):
        self.query_repository = query_repository
        self.cache = cache
        self.logger = logger

    async def handle(self, query: GetBookQuery) -> BookReadModel:
        """Execute the query to get a book."""
        cache_key = self.cache.build_key(self.CACHE_PREFIX, query.book_id)

        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug(f"Cache hit for {cache_key}")
            return BookReadModel(**cached)

        book = await self.query_repository.find_by_id(query.book_id)

        if not book:
            self.logger.warning(f"Book not found: {query.book_id}")
            raise BookNotFoundException(query.book_id)

        self.cache.set(cache_key, book.__dict__)
        self.logger.info(f"Retrieved book: {book.title} (query side)")
        return book

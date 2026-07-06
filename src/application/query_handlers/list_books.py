"""
List Books Query - CQRS Query Side.

Queries are read-only operations that return data from the read model.
They never modify state and can be optimized independently from writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from .read_models import BookReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import IBookQueryRepository
    from src.domain.shared_kernel import ICache, ILogger


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
    limit: int = 20
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

    async def handle(self, query: ListBooksQuery) -> List[BookReadModel]:
        """Execute the query to list books."""
        cache_key = self.cache.build_list_key(
            self.CACHE_PREFIX,
            only_available=query.only_available,
            only_borrowed=query.only_borrowed,
            author_contains=query.author_contains,
            title_contains=query.title_contains,
            limit=query.limit,
            offset=query.offset,
        )

        cached = await self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug(f"Cache hit for {cache_key}")
            return [BookReadModel(**item) for item in cached]

        books = await self.query_repository.find_all(
            only_available=query.only_available,
            only_borrowed=query.only_borrowed,
            author_contains=query.author_contains,
            title_contains=query.title_contains,
            limit=query.limit,
            offset=query.offset,
        )

        await self.cache.set(cache_key, [b.__dict__ for b in books])
        self.logger.info(f"Listed {len(books)} books (query side)")
        return books

"""
List Books Query - CQRS Query Side.

Queries are read-only operations that return data from the read model.
They never modify state and can be optimized independently from writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from .pagination import InvalidPaginationError, QueryPage, validate_pagination
from .read_models import BookReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import IBookQueryRepository
    from src.application.ports import ICache, ILogger


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
    cursor: Optional[str] = None


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
        return (await self.handle_page(query)).items

    async def handle_page(self, query: ListBooksQuery) -> QueryPage[BookReadModel]:
        validate_pagination(
            limit=query.limit, offset=query.offset, cursor=query.cursor
        )
        if query.only_available and query.only_borrowed:
            raise InvalidPaginationError(
                "only_available and only_borrowed are mutually exclusive"
            )
        cache_key = self.cache.build_list_key(
            self.CACHE_PREFIX,
            only_available=query.only_available,
            only_borrowed=query.only_borrowed,
            author_contains=query.author_contains,
            title_contains=query.title_contains,
            limit=query.limit,
            offset=query.offset,
            cursor=query.cursor,
        )

        async def load() -> dict:
            page = await self.query_repository.find_page(
                only_available=query.only_available,
                only_borrowed=query.only_borrowed,
                author_contains=query.author_contains,
                title_contains=query.title_contains,
                limit=query.limit,
                offset=query.offset,
                cursor=query.cursor,
            )
            return {
                "items": [item.__dict__ for item in page.items],
                "next_cursor": page.next_cursor,
                "total": page.total,
            }

        payload = await self.cache.get_or_set(cache_key, load)
        items = [BookReadModel.from_mapping(item) for item in payload["items"]]
        self.logger.info(f"Listed {len(items)} books (query side)")
        return QueryPage(
            items=items,
            next_cursor=payload.get("next_cursor"),
            total=payload.get("total"),
        )

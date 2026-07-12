"""
List Patrons Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from .pagination import QueryPage, validate_pagination
from .read_models import PatronReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import IPatronQueryRepository
    from src.application.ports import ICache, ILogger


@dataclass(frozen=True)
class ListPatronsQuery:
    """Query to list patrons with filters."""
    only_suspended: bool = False
    membership_tier: Optional[str] = None
    limit: int = 20
    offset: int = 0
    cursor: Optional[str] = None


class ListPatronsHandler:
    """Handles listing patrons with caching."""

    CACHE_PREFIX = "patron"

    def __init__(
        self,
        query_repository: IPatronQueryRepository,
        cache: ICache,
        logger: ILogger,
    ):
        self.query_repository = query_repository
        self.cache = cache
        self.logger = logger

    async def handle(self, query: ListPatronsQuery) -> List[PatronReadModel]:
        return (await self.handle_page(query)).items

    async def handle_page(self, query: ListPatronsQuery) -> QueryPage[PatronReadModel]:
        validate_pagination(
            limit=query.limit, offset=query.offset, cursor=query.cursor
        )
        cache_key = self.cache.build_list_key(
            self.CACHE_PREFIX,
            only_suspended=query.only_suspended,
            membership_tier=query.membership_tier,
            limit=query.limit,
            offset=query.offset,
            cursor=query.cursor,
        )

        async def load() -> dict:
            page = await self.query_repository.find_page(
                only_suspended=query.only_suspended,
                membership_tier=query.membership_tier,
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
        return QueryPage(
            items=[PatronReadModel.from_mapping(item) for item in payload["items"]],
            next_cursor=payload.get("next_cursor"),
            total=payload.get("total"),
        )

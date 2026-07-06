"""
List Patrons Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from .read_models import PatronReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import IPatronQueryRepository
    from src.domain.shared_kernel import ICache, ILogger


@dataclass(frozen=True)
class ListPatronsQuery:
    """Query to list patrons with filters."""
    only_suspended: bool = False
    membership_tier: Optional[str] = None
    limit: int = 20
    offset: int = 0


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
        cache_key = self.cache.build_list_key(
            self.CACHE_PREFIX,
            only_suspended=query.only_suspended,
            membership_tier=query.membership_tier,
            limit=query.limit,
            offset=query.offset,
        )

        cached = await self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug(f"Cache hit for {cache_key}")
            return [PatronReadModel(**item) for item in cached]

        results = await self.query_repository.find_all(
            only_suspended=query.only_suspended,
            membership_tier=query.membership_tier,
            limit=query.limit,
            offset=query.offset,
        )

        await self.cache.set(cache_key, [r.__dict__ for r in results])
        return results

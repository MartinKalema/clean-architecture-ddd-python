"""
List Patrons Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.adapters.cache import CacheAdapter
    from src.infrastructure.adapters.patron import PatronQueryRepository


@dataclass(frozen=True)
class PatronReadModel:
    """Read model for Patron."""
    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    membership_tier: str
    is_suspended: bool
    suspended_reason: Optional[str]
    registered_at: datetime


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
        query_repository: PatronQueryRepository,
        cache: CacheAdapter,
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

        await self.cache.set(cache_key, results)
        return [PatronReadModel(**r) for r in results]

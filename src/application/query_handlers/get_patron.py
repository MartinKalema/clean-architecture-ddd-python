"""
Get Patron Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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
class GetPatronQuery:
    """Query to get a patron by ID."""
    patron_id: str


class GetPatronHandler:
    """Handles getting a single patron with caching."""

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

    async def handle(self, query: GetPatronQuery) -> Optional[PatronReadModel]:
        cache_key = self.cache.build_key(self.CACHE_PREFIX, query.patron_id)

        cached = await self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug(f"Cache hit for {cache_key}")
            return PatronReadModel(**cached)

        result = await self.query_repository.find_by_id(query.patron_id)
        if not result:
            return None

        await self.cache.set(cache_key, result)
        return PatronReadModel(**result)

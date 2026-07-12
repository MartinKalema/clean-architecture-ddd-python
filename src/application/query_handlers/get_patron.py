"""
Get Patron Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.patron import PatronNotFoundException

from .read_models import PatronReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import IPatronQueryRepository
    from src.application.ports import ICache, ILogger


@dataclass(frozen=True)
class GetPatronQuery:
    """Query to get a patron by ID."""
    patron_id: str


class GetPatronHandler:
    """Handles getting a single patron with caching."""

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

    async def handle(self, query: GetPatronQuery) -> PatronReadModel:
        cache_key = self.cache.build_key(self.CACHE_PREFIX, query.patron_id)

        async def load() -> dict:
            result = await self.query_repository.find_by_id(query.patron_id)
            if result is None:
                raise PatronNotFoundException(query.patron_id)
            return result.__dict__

        cached = await self.cache.get_or_set(cache_key, load)
        return PatronReadModel.from_mapping(cached)

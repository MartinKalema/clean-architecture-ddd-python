"""
List Patron Loans Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.adapters.cache import CacheAdapter
    from src.infrastructure.adapters.lending import LoanQueryRepository


@dataclass(frozen=True)
class LoanReadModel:
    """Read model for Loan."""
    id: str
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime]
    status: str


@dataclass(frozen=True)
class ListPatronLoansQuery:
    """Query to list loans for a patron."""
    patron_id: str
    only_active: bool = False
    limit: int = 20
    offset: int = 0


class ListPatronLoansHandler:
    """Handles listing loans for a patron with caching."""

    CACHE_PREFIX = "loan"

    def __init__(
        self,
        query_repository: LoanQueryRepository,
        cache: CacheAdapter,
        logger: ILogger,
    ):
        self.query_repository = query_repository
        self.cache = cache
        self.logger = logger

    async def handle(self, query: ListPatronLoansQuery) -> List[LoanReadModel]:
        cache_key = self.cache.build_list_key(
            self.CACHE_PREFIX,
            patron_id=query.patron_id,
            only_active=query.only_active,
            limit=query.limit,
            offset=query.offset,
        )

        cached = await self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug(f"Cache hit for {cache_key}")
            return [LoanReadModel(**item) for item in cached]

        results = await self.query_repository.find_by_patron(
            patron_id=query.patron_id,
            only_active=query.only_active,
            limit=query.limit,
            offset=query.offset,
        )

        await self.cache.set(cache_key, results)
        return [LoanReadModel(**r) for r in results]

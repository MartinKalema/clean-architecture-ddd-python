"""
Get Loan Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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
class GetLoanQuery:
    """Query to get a loan by ID."""
    loan_id: str


class GetLoanHandler:
    """Handles getting a single loan with caching."""

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

    async def handle(self, query: GetLoanQuery) -> Optional[LoanReadModel]:
        cache_key = self.cache.build_key(self.CACHE_PREFIX, query.loan_id)

        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug(f"Cache hit for {cache_key}")
            return LoanReadModel(**cached)

        result = await self.query_repository.find_by_id(query.loan_id)
        if not result:
            return None

        self.cache.set(cache_key, result)
        return LoanReadModel(**result)

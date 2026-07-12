"""
Get Loan Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.lending import LoanNotFoundException

from .read_models import LoanReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import ILoanQueryRepository
    from src.application.ports import ICache, ILogger


@dataclass(frozen=True)
class GetLoanQuery:
    """Query to get a loan by ID."""
    loan_id: str


class GetLoanHandler:
    """Handles getting a single loan with caching."""

    CACHE_PREFIX = "loan"

    def __init__(
        self,
        query_repository: ILoanQueryRepository,
        cache: ICache,
        logger: ILogger,
    ):
        self.query_repository = query_repository
        self.cache = cache
        self.logger = logger

    async def handle(self, query: GetLoanQuery) -> LoanReadModel:
        cache_key = self.cache.build_key(self.CACHE_PREFIX, query.loan_id)

        async def load() -> dict:
            result = await self.query_repository.find_by_id(query.loan_id)
            if result is None:
                raise LoanNotFoundException(query.loan_id)
            return result.__dict__

        cached = await self.cache.get_or_set(cache_key, load)
        return LoanReadModel.from_mapping(cached)

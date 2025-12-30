"""
List Patron Loans Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.domain.shared_kernel import Logger
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
    limit: int = 100
    offset: int = 0


class ListPatronLoansHandler:
    """Handles listing loans for a patron."""

    def __init__(self, query_repository: LoanQueryRepository, logger: Logger):
        self.query_repository = query_repository
        self.logger = logger

    async def handle(self, query: ListPatronLoansQuery) -> List[LoanReadModel]:
        results = await self.query_repository.find_by_patron(
            patron_id=query.patron_id,
            only_active=query.only_active,
            limit=query.limit,
            offset=query.offset,
        )
        return [LoanReadModel(**r) for r in results]

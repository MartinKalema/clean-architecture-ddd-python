"""
List Patron Loans Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from .pagination import QueryPage, validate_pagination
from .read_models import LoanReadModel

if TYPE_CHECKING:
    from src.application.query_handlers.interfaces import ILoanQueryRepository
    from src.application.ports import ICache, ILogger


@dataclass(frozen=True)
class ListPatronLoansQuery:
    """Query to list loans for a patron."""
    patron_id: str
    only_active: bool = False
    limit: int = 20
    offset: int = 0
    cursor: Optional[str] = None


class ListPatronLoansHandler:
    """Handles listing loans for a patron with caching."""

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

    async def handle(self, query: ListPatronLoansQuery) -> List[LoanReadModel]:
        return (await self.handle_page(query)).items

    async def handle_page(
        self, query: ListPatronLoansQuery
    ) -> QueryPage[LoanReadModel]:
        validate_pagination(
            limit=query.limit, offset=query.offset, cursor=query.cursor
        )
        cache_key = self.cache.build_list_key(
            self.CACHE_PREFIX,
            patron_id=query.patron_id,
            only_active=query.only_active,
            limit=query.limit,
            offset=query.offset,
            cursor=query.cursor,
        )

        async def load() -> dict:
            page = await self.query_repository.find_by_patron_page(
                patron_id=query.patron_id,
                only_active=query.only_active,
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
            items=[LoanReadModel.from_mapping(item) for item in payload["items"]],
            next_cursor=payload.get("next_cursor"),
            total=payload.get("total"),
        )

"""
Loan Query Repository - CQRS Read Side Implementation.

Implements: ILoanQueryRepository

Uses PostgreSQL for point lookups (find_by_id) and Elasticsearch
for search/aggregation operations (find_by_patron, find_overdue).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.adapters.lending.loan_model import LoanModel

if TYPE_CHECKING:
    from src.infrastructure.external.elasticsearch_client import ElasticsearchClient


class LoanQueryRepository:
    """
    Loan Query Repository implementation.

    Uses a hybrid approach:
    - PostgreSQL for point lookups (O(1) by ID)
    - Elasticsearch for search/filter operations (full-text search, aggregations)
    """

    ES_INDEX = "loans"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        elasticsearch_client: ElasticsearchClient,
    ):
        self._session_factory = session_factory
        self._es_client = elasticsearch_client

    async def find_by_id(self, loan_id: str) -> Optional[dict]:
        """Find a loan by ID (uses PostgreSQL for consistency)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(LoanModel).where(LoanModel.id == loan_id)
            )
            loan = result.scalar_one_or_none()
            if not loan:
                return None
            return self._to_read_model_from_db(loan)

    async def find_by_patron(
        self,
        patron_id: str,
        only_active: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Find loans for a patron (uses Elasticsearch for search)."""
        query = self._build_es_query(
            patron_id=patron_id,
            only_active=only_active,
        )

        result = self._es_client.search(
            index=self.ES_INDEX,
            query=query,
            size=limit,
            from_=offset,
        )

        return [
            self._to_read_model_from_es(hit)
            for hit in result["hits"]
        ]

    async def find_overdue(self, limit: int = 100) -> List[dict]:
        """Find overdue loans (uses Elasticsearch for search)."""
        query = {"bool": {"filter": [{"term": {"is_overdue": True}}]}}

        result = self._es_client.search(
            index=self.ES_INDEX,
            query=query,
            size=limit,
        )

        return [
            self._to_read_model_from_es(hit)
            for hit in result["hits"]
        ]

    def _build_es_query(
        self,
        patron_id: Optional[str] = None,
        only_active: bool = False,
    ) -> dict[str, Any]:
        """Build Elasticsearch query from filter parameters."""
        filter_clauses: list[dict[str, Any]] = []

        if patron_id:
            filter_clauses.append({"term": {"patron_id": patron_id}})

        if only_active:
            filter_clauses.append({"term": {"status": "active"}})

        if filter_clauses:
            return {"bool": {"filter": filter_clauses}}
        return {"match_all": {}}

    def _to_read_model_from_db(self, loan: LoanModel) -> dict:
        """Convert database row to read model."""
        return {
            "id": loan.id,
            "patron_id": loan.patron_id,
            "patron_email": loan.patron_email,
            "catalog_book_id": loan.catalog_book_id,
            "book_title": loan.book_title,
            "borrowed_at": loan.borrowed_at,
            "due_date": loan.due_date,
            "returned_at": loan.returned_at,
            "status": loan.status,
        }

    def _to_read_model_from_es(self, hit: dict[str, Any]) -> dict:
        """Convert Elasticsearch hit to read model."""
        return {
            "id": hit["id"],
            "patron_id": hit.get("patron_id", ""),
            "patron_email": hit.get("patron_email", ""),
            "catalog_book_id": hit.get("catalog_book_id", ""),
            "book_title": hit.get("book_title", ""),
            "borrowed_at": hit.get("borrowed_at"),
            "due_date": hit.get("due_date"),
            "returned_at": hit.get("returned_at"),
            "status": hit.get("status", ""),
        }

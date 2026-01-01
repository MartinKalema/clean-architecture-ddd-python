"""
Patron Query Repository - CQRS Read Side Implementation.

Implements: IPatronQueryRepository

Uses PostgreSQL for point lookups (find_by_id, find_by_email) and
Elasticsearch for search/aggregation operations (find_all, count).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.adapters.patron.patron_model import PatronModel

if TYPE_CHECKING:
    from src.infrastructure.external.elasticsearch_client import ElasticsearchClient


class PatronQueryRepository:
    """
    Patron Query Repository implementation.

    Uses a hybrid approach:
    - PostgreSQL for point lookups (O(1) by ID/email)
    - Elasticsearch for search/filter operations (full-text search, aggregations)
    """

    ES_INDEX = "patrons"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        elasticsearch_client: ElasticsearchClient,
    ):
        self._session_factory = session_factory
        self._es_client = elasticsearch_client

    async def find_by_id(self, patron_id: str) -> Optional[dict]:
        """Find a patron by ID (uses PostgreSQL for consistency)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.id == patron_id)
            )
            patron = result.scalar_one_or_none()
            if not patron:
                return None
            return self._to_read_model_from_db(patron)

    async def find_by_email(self, email: str) -> Optional[dict]:
        """Find a patron by email (uses PostgreSQL for consistency)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.email == email)
            )
            patron = result.scalar_one_or_none()
            if not patron:
                return None
            return self._to_read_model_from_db(patron)

    async def find_all(
        self,
        only_suspended: bool = False,
        membership_tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Find patrons with optional filters (uses Elasticsearch for search)."""
        query = self._build_es_query(
            only_suspended=only_suspended,
            membership_tier=membership_tier,
        )

        result = await self._es_client.search(
            index=self.ES_INDEX,
            query=query,
            size=limit,
            from_=offset,
        )

        return [
            self._to_read_model_from_es(hit)
            for hit in result["hits"]
        ]

    async def count(self, only_suspended: bool = False) -> int:
        """Count patrons matching criteria (uses Elasticsearch)."""
        query = self._build_es_query(only_suspended=only_suspended)

        result = await self._es_client.search(
            index=self.ES_INDEX,
            query=query,
            size=0,
        )

        return result["total"]

    def _build_es_query(
        self,
        only_suspended: bool = False,
        membership_tier: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build Elasticsearch query from filter parameters."""
        filter_clauses: list[dict[str, Any]] = []

        if only_suspended:
            filter_clauses.append({"term": {"is_suspended": True}})

        if membership_tier:
            filter_clauses.append({"term": {"membership_tier": membership_tier}})

        if filter_clauses:
            return {"bool": {"filter": filter_clauses}}
        return {"match_all": {}}

    def _to_read_model_from_db(self, patron: PatronModel) -> dict:
        """Convert database row to read model."""
        return {
            "id": patron.id,
            "first_name": patron.first_name,
            "last_name": patron.last_name,
            "name": f"{patron.first_name} {patron.last_name}",
            "email": patron.email,
            "membership_tier": patron.membership_tier,
            "is_suspended": patron.is_suspended,
            "suspended_reason": patron.suspended_reason,
            "registered_at": patron.registered_at,
        }

    def _to_read_model_from_es(self, hit: dict[str, Any]) -> dict:
        """Convert Elasticsearch hit to read model."""
        return {
            "id": hit["id"],
            "first_name": hit.get("first_name", ""),
            "last_name": hit.get("last_name", ""),
            "name": hit.get("full_name", ""),
            "email": hit.get("email", ""),
            "membership_tier": hit.get("membership_tier"),
            "is_suspended": hit.get("is_suspended", False),
            "suspended_reason": hit.get("suspended_reason"),
            "registered_at": hit.get("registered_at"),
        }

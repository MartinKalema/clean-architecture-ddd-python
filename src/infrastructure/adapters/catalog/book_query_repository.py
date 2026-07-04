"""
Book Query Repository - CQRS Read Side Implementation.

Implements: IBookQueryRepository

Uses PostgreSQL for point lookups (find_by_id) and Elasticsearch
for search/aggregation operations (find_all, count).

Elasticsearch calls are protected by a circuit breaker; when ES is
unavailable (or the circuit is open) searches degrade to PostgreSQL —
without fuzzy matching or relevance scoring, but correct and available.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.query_handlers import BookReadModel
from src.infrastructure.adapters.catalog.book_model import BookModel
from src.infrastructure.exceptions import (
    CircuitBreakerOpenException,
    SearchEngineException,
)

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.adapters.resilience import CircuitBreaker
    from src.infrastructure.external.elasticsearch_client import ElasticsearchClient


class BookQueryRepository:
    """
    Book Query Repository implementation.

    Uses a hybrid approach:
    - PostgreSQL for point lookups (O(1) by ID)
    - Elasticsearch for search/filter operations (full-text search, aggregations)
    - PostgreSQL fallback when Elasticsearch is unavailable
    """

    ES_INDEX = "books"

    def __init__(
        self,
        session_factory: async_sessionmaker,
        elasticsearch_client: ElasticsearchClient,
        circuit_breaker: CircuitBreaker,
        logger: ILogger,
    ):
        self._session_factory = session_factory
        self._es_client = elasticsearch_client
        self._circuit_breaker = circuit_breaker
        self._logger = logger

    async def find_by_id(self, book_id: str) -> Optional[BookReadModel]:
        """Find a book by its ID (uses PostgreSQL for consistency)."""
        async with self._session_factory() as session:
            stmt = select(BookModel).where(BookModel.id == book_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if not row:
                return None

            return self._to_read_model_from_db(row)

    async def find_all(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
        author_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BookReadModel]:
        """Find books with optional filters (uses Elasticsearch for search)."""
        query = self._build_es_query(
            only_available=only_available,
            only_borrowed=only_borrowed,
            author_contains=author_contains,
            title_contains=title_contains,
        )

        try:
            result = await self._circuit_breaker.execute(
                self._es_client.search,
                index=self.ES_INDEX,
                query=query,
                size=limit,
                from_=offset,
            )
        except (SearchEngineException, CircuitBreakerOpenException) as e:
            self._logger.warning(
                f"Elasticsearch unavailable for book search, "
                f"falling back to PostgreSQL: {e}"
            )
            return await self._find_all_from_db(
                only_available=only_available,
                only_borrowed=only_borrowed,
                author_contains=author_contains,
                title_contains=title_contains,
                limit=limit,
                offset=offset,
            )

        return [
            self._to_read_model_from_es(hit)
            for hit in result["hits"]
        ]

    async def count(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
    ) -> int:
        """Count books matching criteria (uses Elasticsearch)."""
        query = self._build_es_query(
            only_available=only_available,
            only_borrowed=only_borrowed,
        )

        try:
            return await self._circuit_breaker.execute(
                self._es_client.count,
                index=self.ES_INDEX,
                query=query,
            )
        except (SearchEngineException, CircuitBreakerOpenException) as e:
            self._logger.warning(
                f"Elasticsearch unavailable for book count, "
                f"falling back to PostgreSQL: {e}"
            )
            return await self._count_from_db(
                only_available=only_available,
                only_borrowed=only_borrowed,
            )

    async def _find_all_from_db(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
        author_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BookReadModel]:
        """PostgreSQL fallback for find_all (substring match, no fuzziness)."""
        stmt = select(BookModel)

        if title_contains:
            stmt = stmt.where(BookModel.title.ilike(f"%{title_contains}%"))
        if author_contains:
            stmt = stmt.where(BookModel.author.ilike(f"%{author_contains}%"))
        if only_available:
            stmt = stmt.where(BookModel.is_borrowed.is_(False))
        elif only_borrowed:
            stmt = stmt.where(BookModel.is_borrowed.is_(True))

        stmt = stmt.order_by(BookModel.title).limit(limit).offset(offset)

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return [self._to_read_model_from_db(row) for row in result.scalars().all()]

    async def _count_from_db(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
    ) -> int:
        """PostgreSQL fallback for count."""
        stmt = select(func.count()).select_from(BookModel)

        if only_available:
            stmt = stmt.where(BookModel.is_borrowed.is_(False))
        elif only_borrowed:
            stmt = stmt.where(BookModel.is_borrowed.is_(True))

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return result.scalar_one()

    def _build_es_query(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
        author_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build Elasticsearch query from filter parameters."""
        must: list[dict[str, Any]] = []
        filter_clauses: list[dict[str, Any]] = []

        # Text search (use must for relevance scoring)
        if title_contains:
            must.append({
                "match": {
                    "title": {
                        "query": title_contains,
                        "fuzziness": "AUTO",
                    }
                }
            })

        if author_contains:
            must.append({
                "match": {
                    "author": {
                        "query": author_contains,
                        "fuzziness": "AUTO",
                    }
                }
            })

        # Boolean filters (use filter for exact matching)
        if only_available:
            filter_clauses.append({"term": {"is_borrowed": False}})
        elif only_borrowed:
            filter_clauses.append({"term": {"is_borrowed": True}})

        # Build final query
        if must or filter_clauses:
            return {
                "bool": {
                    "must": must if must else [{"match_all": {}}],
                    "filter": filter_clauses,
                }
            }
        return {"match_all": {}}

    def _to_read_model_from_db(self, row: BookModel) -> BookReadModel:
        """Convert database row to read model."""
        return BookReadModel(
            id=row.id,
            title=row.title,
            author=row.author,
            is_borrowed=row.is_borrowed,
            borrowed_at=row.borrowed_at,
            return_due_date=row.return_due_date,
        )

    def _to_read_model_from_es(self, hit: dict[str, Any]) -> BookReadModel:
        """Convert Elasticsearch hit to read model."""
        return BookReadModel(
            id=hit["id"],
            title=hit.get("title", ""),
            author=hit.get("author", ""),
            is_borrowed=hit.get("is_borrowed", False),
            borrowed_at=hit.get("borrowed_at"),
            return_due_date=hit.get("return_due_date"),
        )

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

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.query_handlers import BookReadModel, QueryPage
from src.application.query_handlers.pagination import (
    cursor_string,
    cursor_scope,
    decode_cursor_with_backend,
    encode_cursor,
    validate_pagination,
)
from src.infrastructure.adapters.catalog.book_model import BookModel
from src.infrastructure.exceptions import (
    CircuitBreakerOpenException,
    SearchEngineException,
)

if TYPE_CHECKING:
    from src.application.ports import ILogger
    from src.infrastructure.adapters.cdc.kafka_projection_freshness import (
        KafkaProjectionFreshness,
    )
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
    ES_SORT: list[dict[str, Any]] = [
        {"title.sort": {"order": "asc", "missing": "_last"}},
        {"id": {"order": "asc"}},
    ]

    def __init__(
        self,
        session_factory: async_sessionmaker,
        elasticsearch_client: ElasticsearchClient,
        circuit_breaker: CircuitBreaker,
        logger: ILogger,
        search_enabled: bool = True,
        projection_freshness: KafkaProjectionFreshness | None = None,
    ):
        self._session_factory = session_factory
        self._es_client = elasticsearch_client
        self._circuit_breaker = circuit_breaker
        self._logger = logger
        self._search_enabled = search_enabled
        self._projection_freshness = projection_freshness

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
        page = await self.find_page(
            only_available=only_available,
            only_borrowed=only_borrowed,
            author_contains=author_contains,
            title_contains=title_contains,
            limit=limit,
            offset=offset,
        )
        return page.items

    async def find_page(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
        author_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        cursor: str | None = None,
    ) -> QueryPage[BookReadModel]:
        """Return a stable title/id page; cursors avoid deep offsets."""
        validate_pagination(limit=limit, offset=offset, cursor=cursor)
        scope = cursor_scope(
            "books",
            {
                "only_available": only_available,
                "only_borrowed": only_borrowed,
                "author_contains": author_contains,
                "title_contains": title_contains,
            },
        )
        cursor_backend = None
        search_after = None
        if cursor:
            search_after, cursor_backend = decode_cursor_with_backend(
                cursor, expected_scope=scope, expected_values=2
            )
        if search_after is not None:
            search_after = [
                cursor_string(
                    search_after[0], field="title sort value", max_length=100
                ),
                cursor_string(
                    search_after[1],
                    field="book id",
                    max_length=64,
                    pattern=r"[A-Za-z0-9][A-Za-z0-9_-]*",
                ),
            ]
        query = self._build_es_query(
            only_available=only_available,
            only_borrowed=only_borrowed,
            author_contains=author_contains,
            title_contains=title_contains,
        )

        search_fresh = await self._search_is_fresh()
        if not search_fresh or cursor_backend == "postgresql":
            if cursor_backend == "elasticsearch":
                raise SearchEngineException(
                    "This page cursor is pinned to Elasticsearch, which is disabled or lagging"
                )
            return await self._find_page_from_db(
                only_available=only_available,
                only_borrowed=only_borrowed,
                author_contains=author_contains,
                title_contains=title_contains,
                limit=limit,
                offset=offset,
                cursor_values=search_after,
                cursor_scope_value=scope,
            )

        try:
            result = await self._circuit_breaker.execute(
                self._es_client.search,
                index=self.ES_INDEX,
                query=query,
                size=limit,
                from_=offset,
                sort=self.ES_SORT,
                search_after=search_after,
            )
        except (SearchEngineException, CircuitBreakerOpenException) as e:
            if cursor_backend == "elasticsearch":
                raise
            self._logger.warning(
                f"Elasticsearch unavailable for book search, "
                f"falling back to PostgreSQL: {e}"
            )
            return await self._find_page_from_db(
                only_available=only_available,
                only_borrowed=only_borrowed,
                author_contains=author_contains,
                title_contains=title_contains,
                limit=limit,
                offset=offset,
                cursor_values=search_after,
                cursor_scope_value=scope,
            )

        hits = result["hits"]
        try:
            items = [self._to_read_model_from_es(hit) for hit in hits]
        except (KeyError, TypeError, ValueError) as e:
            if cursor_backend == "elasticsearch":
                raise SearchEngineException(
                    "Elasticsearch returned an invalid document for a pinned cursor",
                    original_exception=e,
                ) from e
            self._logger.warning(
                f"Invalid Elasticsearch book document; falling back to PostgreSQL: {e}"
            )
            return await self._find_page_from_db(
                only_available=only_available,
                only_borrowed=only_borrowed,
                author_contains=author_contains,
                title_contains=title_contains,
                limit=limit,
                offset=offset,
                cursor_values=search_after,
                cursor_scope_value=scope,
            )
        next_cursor = None
        if len(hits) == limit and hits:
            sort_values = hits[-1].get("_sort") or [
                items[-1].title.lower(),
                items[-1].id,
            ]
            next_cursor = encode_cursor(
                scope, sort_values, backend="elasticsearch"
            )
        return QueryPage(items=items, next_cursor=next_cursor, total=result.get("total"))

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

        if not await self._search_is_fresh():
            return await self._count_from_db(
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

    async def _search_is_fresh(self) -> bool:
        if not self._search_enabled:
            return False
        if self._projection_freshness is None:
            return True
        return await self._projection_freshness.is_fresh()

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
        page = await self._find_page_from_db(
            only_available=only_available,
            only_borrowed=only_borrowed,
            author_contains=author_contains,
            title_contains=title_contains,
            limit=limit,
            offset=offset,
            cursor_values=None,
            cursor_scope_value=cursor_scope(
                "books",
                {
                    "only_available": only_available,
                    "only_borrowed": only_borrowed,
                    "author_contains": author_contains,
                    "title_contains": title_contains,
                },
            ),
        )
        return page.items

    async def _find_page_from_db(
        self,
        *,
        only_available: bool,
        only_borrowed: bool,
        author_contains: Optional[str],
        title_contains: Optional[str],
        limit: int,
        offset: int,
        cursor_values: list[Any] | None,
        cursor_scope_value: str,
    ) -> QueryPage[BookReadModel]:
        stmt = select(BookModel)

        if title_contains:
            stmt = stmt.where(
                BookModel.title.ilike(_contains_pattern(title_contains), escape="\\")
            )
        if author_contains:
            stmt = stmt.where(
                BookModel.author.ilike(_contains_pattern(author_contains), escape="\\")
            )
        if only_available:
            stmt = stmt.where(BookModel.status == "available")
        elif only_borrowed:
            stmt = stmt.where(BookModel.status == "borrowed")

        if cursor_values is not None:
            title, book_id = (str(value) for value in cursor_values)
            stmt = stmt.where(
                or_(
                    func.lower(BookModel.title) > title,
                    and_(func.lower(BookModel.title) == title, BookModel.id > book_id),
                )
            )

        stmt = (
            stmt.order_by(func.lower(BookModel.title), BookModel.id)
            .limit(limit)
            .offset(offset)
        )

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            items = [self._to_read_model_from_db(row) for row in result.scalars().all()]
        next_cursor = None
        if len(items) == limit and items:
            next_cursor = encode_cursor(
                cursor_scope_value,
                [items[-1].title.lower(), items[-1].id],
                backend="postgresql",
            )
        return QueryPage(items=items, next_cursor=next_cursor)

    async def _count_from_db(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
    ) -> int:
        """PostgreSQL fallback for count."""
        stmt = select(func.count()).select_from(BookModel)

        if only_available:
            stmt = stmt.where(BookModel.status == "available")
        elif only_borrowed:
            stmt = stmt.where(BookModel.status == "borrowed")

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

        # Status filters (use filter for exact matching). A RESERVED book
        # is neither available (semantic lock held) nor borrowed (tentative)
        if only_available:
            filter_clauses.append({"term": {"status": "available"}})
        elif only_borrowed:
            filter_clauses.append({"term": {"status": "borrowed"}})

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
            is_borrowed=row.status == "borrowed",
            status=row.status,
            borrowed_at=row.borrowed_at,
            return_due_date=row.return_due_date,
        )

    def _to_read_model_from_es(self, hit: dict[str, Any]) -> BookReadModel:
        """Convert Elasticsearch hit to read model."""
        status = hit.get("status", "available")
        return BookReadModel.from_mapping({**hit, "status": status})


def _contains_pattern(value: str) -> str:
    """Treat user text literally while retaining trigram-indexed substring search."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

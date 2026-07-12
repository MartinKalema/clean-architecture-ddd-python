"""
Patron Query Repository - CQRS Read Side Implementation.

Implements: IPatronQueryRepository

Uses PostgreSQL for point lookups (find_by_id, find_by_email) and
Elasticsearch for search/aggregation operations (find_all, count).

Elasticsearch calls are protected by a circuit breaker; when ES is
unavailable (or the circuit is open) searches degrade to PostgreSQL.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.query_handlers.pagination import (
    InvalidPaginationError,
    QueryPage,
    cursor_string,
    cursor_scope,
    decode_cursor_with_backend,
    encode_cursor,
    validate_pagination,
)
from src.application.query_handlers.read_models import PatronReadModel
from src.infrastructure.adapters.patron.patron_model import PatronModel
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


class PatronQueryRepository:
    """
    Patron Query Repository implementation.

    Uses a hybrid approach:
    - PostgreSQL for point lookups (O(1) by ID/email)
    - Elasticsearch for search/filter operations (full-text search, aggregations)
    - PostgreSQL fallback when Elasticsearch is unavailable
    """

    ES_INDEX = "patrons"
    ES_SORT: list[dict[str, Any]] = [
        {
            "registered_at": {
                "order": "asc",
                "missing": "_last",
                "format": "strict_date_time_nanos",
            }
        },
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

    async def find_by_id(self, patron_id: str) -> Optional[PatronReadModel]:
        """Find a patron by ID (uses PostgreSQL for consistency)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.id == patron_id)
            )
            patron = result.scalar_one_or_none()
            if not patron:
                return None
            return self._to_read_model_from_db(patron)

    async def find_by_email(self, email: str) -> Optional[PatronReadModel]:
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
    ) -> List[PatronReadModel]:
        """Find patrons with optional filters (uses Elasticsearch for search)."""
        page = await self.find_page(
            only_suspended=only_suspended,
            membership_tier=membership_tier,
            limit=limit,
            offset=offset,
        )
        return page.items

    async def find_page(
        self,
        only_suspended: bool = False,
        membership_tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        cursor: str | None = None,
    ) -> QueryPage[PatronReadModel]:
        validate_pagination(limit=limit, offset=offset, cursor=cursor)
        scope = cursor_scope(
            "patrons",
            {
                "only_suspended": only_suspended,
                "membership_tier": membership_tier,
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
                _cursor_datetime(search_after[0]).isoformat(),
                cursor_string(
                    search_after[1],
                    field="patron id",
                    max_length=64,
                    pattern=r"[A-Za-z0-9][A-Za-z0-9_-]*",
                ),
            ]
        query = self._build_es_query(
            only_suspended=only_suspended,
            membership_tier=membership_tier,
        )

        search_fresh = await self._search_is_fresh()
        if not search_fresh or cursor_backend == "postgresql":
            if cursor_backend == "elasticsearch":
                raise SearchEngineException(
                    "This page cursor is pinned to Elasticsearch, which is disabled or lagging"
                )
            return await self._find_page_from_db(
                only_suspended=only_suspended,
                membership_tier=membership_tier,
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
                f"Elasticsearch unavailable for patron search, "
                f"falling back to PostgreSQL: {e}"
            )
            return await self._find_page_from_db(
                only_suspended=only_suspended,
                membership_tier=membership_tier,
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
                f"Invalid Elasticsearch patron document; falling back to PostgreSQL: {e}"
            )
            return await self._find_page_from_db(
                only_suspended=only_suspended,
                membership_tier=membership_tier,
                limit=limit,
                offset=offset,
                cursor_values=search_after,
                cursor_scope_value=scope,
            )
        next_cursor = None
        if len(hits) == limit and hits:
            sort_values = hits[-1].get("_sort") or [
                items[-1].registered_at,
                items[-1].id,
            ]
            next_cursor = encode_cursor(
                scope, sort_values, backend="elasticsearch"
            )
        return QueryPage(items=items, next_cursor=next_cursor, total=result.get("total"))

    async def count(self, only_suspended: bool = False) -> int:
        """Count patrons matching criteria (uses Elasticsearch)."""
        query = self._build_es_query(only_suspended=only_suspended)

        if not await self._search_is_fresh():
            return await self._count_from_db(only_suspended=only_suspended)

        try:
            return await self._circuit_breaker.execute(
                self._es_client.count,
                index=self.ES_INDEX,
                query=query,
            )
        except (SearchEngineException, CircuitBreakerOpenException) as e:
            self._logger.warning(
                f"Elasticsearch unavailable for patron count, "
                f"falling back to PostgreSQL: {e}"
            )
            return await self._count_from_db(only_suspended=only_suspended)

    async def _search_is_fresh(self) -> bool:
        if not self._search_enabled:
            return False
        if self._projection_freshness is None:
            return True
        return await self._projection_freshness.is_fresh()

    async def _find_all_from_db(
        self,
        only_suspended: bool = False,
        membership_tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[PatronReadModel]:
        """PostgreSQL fallback for find_all."""
        page = await self._find_page_from_db(
            only_suspended=only_suspended,
            membership_tier=membership_tier,
            limit=limit,
            offset=offset,
            cursor_values=None,
            cursor_scope_value=cursor_scope(
                "patrons",
                {
                    "only_suspended": only_suspended,
                    "membership_tier": membership_tier,
                },
            ),
        )
        return page.items

    async def _find_page_from_db(
        self,
        *,
        only_suspended: bool,
        membership_tier: Optional[str],
        limit: int,
        offset: int,
        cursor_values: list[Any] | None,
        cursor_scope_value: str,
    ) -> QueryPage[PatronReadModel]:
        stmt = select(PatronModel)

        if only_suspended:
            stmt = stmt.where(PatronModel.is_suspended.is_(True))
        if membership_tier:
            stmt = stmt.where(PatronModel.membership_tier == membership_tier)

        if cursor_values is not None:
            registered_at = _cursor_datetime(cursor_values[0])
            patron_id = str(cursor_values[1])
            stmt = stmt.where(
                or_(
                    PatronModel.registered_at > registered_at,
                    and_(
                        PatronModel.registered_at == registered_at,
                        PatronModel.id > patron_id,
                    ),
                )
            )

        stmt = (
            stmt.order_by(PatronModel.registered_at, PatronModel.id)
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
                [items[-1].registered_at, items[-1].id],
                backend="postgresql",
            )
        return QueryPage(items=items, next_cursor=next_cursor)

    async def _count_from_db(self, only_suspended: bool = False) -> int:
        """PostgreSQL fallback for count."""
        stmt = select(func.count()).select_from(PatronModel)

        if only_suspended:
            stmt = stmt.where(PatronModel.is_suspended.is_(True))

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return result.scalar_one()

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

    def _to_read_model_from_db(self, patron: PatronModel) -> PatronReadModel:
        """Convert database row to read model."""
        return PatronReadModel(
            id=patron.id,
            first_name=patron.first_name,
            last_name=patron.last_name,
            name=f"{patron.first_name} {patron.last_name}",
            email=patron.email,
            membership_tier=patron.membership_tier,
            is_suspended=patron.is_suspended,
            suspended_reason=patron.suspended_reason,
            registered_at=patron.registered_at,
        )

    def _to_read_model_from_es(self, hit: dict[str, Any]) -> PatronReadModel:
        """Convert Elasticsearch hit to read model."""
        return PatronReadModel.from_mapping(hit)


def _cursor_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if result.tzinfo is None:
                return result.replace(tzinfo=timezone.utc)
            return result.astimezone(timezone.utc)
        except ValueError as exc:
            raise InvalidPaginationError("cursor contains an invalid datetime") from exc
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1_000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise InvalidPaginationError(
                "cursor contains an invalid datetime"
            ) from exc
    raise InvalidPaginationError("cursor contains an invalid datetime")

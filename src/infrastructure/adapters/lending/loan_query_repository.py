"""
Loan Query Repository - CQRS Read Side Implementation.

Implements: ILoanQueryRepository

Uses PostgreSQL for point lookups (find_by_id) and Elasticsearch
for search/aggregation operations (find_by_patron, find_overdue).

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
from src.application.query_handlers.read_models import LoanReadModel
from src.infrastructure.adapters.lending.loan_model import LoanModel
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


class LoanQueryRepository:
    """
    Loan Query Repository implementation.

    Uses a hybrid approach:
    - PostgreSQL for point lookups (O(1) by ID)
    - Elasticsearch for search/filter operations (full-text search, aggregations)
    - PostgreSQL fallback when Elasticsearch is unavailable
    """

    ES_INDEX = "loans"
    TERMINAL_STATUSES = ("returned", "cancelled")
    PATRON_SORT: list[dict[str, Any]] = [
        {
            "borrowed_at": {
                "order": "desc",
                "missing": "_last",
                "format": "strict_date_time_nanos",
            }
        },
        {"id": {"order": "asc"}},
    ]
    OVERDUE_SORT: list[dict[str, Any]] = [
        {
            "due_date": {
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

    async def find_by_id(self, loan_id: str) -> Optional[LoanReadModel]:
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
    ) -> List[LoanReadModel]:
        """Find loans for a patron (uses Elasticsearch for search)."""
        page = await self.find_by_patron_page(
            patron_id=patron_id,
            only_active=only_active,
            limit=limit,
            offset=offset,
        )
        return page.items

    async def find_by_patron_page(
        self,
        patron_id: str,
        only_active: bool = False,
        limit: int = 100,
        offset: int = 0,
        cursor: str | None = None,
    ) -> QueryPage[LoanReadModel]:
        validate_pagination(limit=limit, offset=offset, cursor=cursor)
        scope = cursor_scope(
            "patron-loans",
            {"patron_id": patron_id, "only_active": only_active},
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
                    field="loan id",
                    max_length=64,
                    pattern=r"[A-Za-z0-9][A-Za-z0-9_-]*",
                ),
            ]
        query = self._build_es_query(
            patron_id=patron_id,
            only_active=only_active,
        )

        search_fresh = await self._search_is_fresh()
        if not search_fresh or cursor_backend == "postgresql":
            if cursor_backend == "elasticsearch":
                raise SearchEngineException(
                    "This page cursor is pinned to Elasticsearch, which is disabled or lagging"
                )
            return await self._find_by_patron_page_from_db(
                patron_id=patron_id,
                only_active=only_active,
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
                sort=self.PATRON_SORT,
                search_after=search_after,
            )
        except (SearchEngineException, CircuitBreakerOpenException) as e:
            if cursor_backend == "elasticsearch":
                raise
            self._logger.warning(
                f"Elasticsearch unavailable for loan search, "
                f"falling back to PostgreSQL: {e}"
            )
            return await self._find_by_patron_page_from_db(
                patron_id=patron_id,
                only_active=only_active,
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
                f"Invalid Elasticsearch loan document; falling back to PostgreSQL: {e}"
            )
            return await self._find_by_patron_page_from_db(
                patron_id=patron_id,
                only_active=only_active,
                limit=limit,
                offset=offset,
                cursor_values=search_after,
                cursor_scope_value=scope,
            )
        next_cursor = None
        if len(hits) == limit and hits:
            sort_values = hits[-1].get("_sort") or [
                items[-1].borrowed_at,
                items[-1].id,
            ]
            next_cursor = encode_cursor(
                scope, sort_values, backend="elasticsearch"
            )
        return QueryPage(items=items, next_cursor=next_cursor, total=result.get("total"))

    async def find_overdue(self, limit: int = 100) -> List[LoanReadModel]:
        """Find overdue loans (uses Elasticsearch for search)."""
        validate_pagination(limit=limit)
        now = datetime.now(timezone.utc).isoformat()
        query = {
            "bool": {
                "filter": [
                    {"range": {"due_date": {"lt": now}}},
                ],
                "must_not": [
                    {"terms": {"status": list(self.TERMINAL_STATUSES)}}
                ],
            }
        }

        if not await self._search_is_fresh():
            return await self._find_overdue_from_db(limit=limit)

        try:
            result = await self._circuit_breaker.execute(
                self._es_client.search,
                index=self.ES_INDEX,
                query=query,
                size=limit,
                sort=self.OVERDUE_SORT,
            )
        except (SearchEngineException, CircuitBreakerOpenException) as e:
            self._logger.warning(
                f"Elasticsearch unavailable for overdue loan search, "
                f"falling back to PostgreSQL: {e}"
            )
            return await self._find_overdue_from_db(limit=limit)

        try:
            return [self._to_read_model_from_es(hit) for hit in result["hits"]]
        except (KeyError, TypeError, ValueError) as e:
            self._logger.warning(
                f"Invalid Elasticsearch loan document; falling back to PostgreSQL: {e}"
            )
            return await self._find_overdue_from_db(limit=limit)

    async def _search_is_fresh(self) -> bool:
        if not self._search_enabled:
            return False
        if self._projection_freshness is None:
            return True
        return await self._projection_freshness.is_fresh()

    async def _find_by_patron_from_db(
        self,
        patron_id: str,
        only_active: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LoanReadModel]:
        """PostgreSQL fallback for find_by_patron."""
        page = await self._find_by_patron_page_from_db(
            patron_id=patron_id,
            only_active=only_active,
            limit=limit,
            offset=offset,
            cursor_values=None,
            cursor_scope_value=cursor_scope(
                "patron-loans",
                {"patron_id": patron_id, "only_active": only_active},
            ),
        )
        return page.items

    async def _find_by_patron_page_from_db(
        self,
        *,
        patron_id: str,
        only_active: bool,
        limit: int,
        offset: int,
        cursor_values: list[Any] | None,
        cursor_scope_value: str,
    ) -> QueryPage[LoanReadModel]:
        stmt = select(LoanModel).where(LoanModel.patron_id == patron_id)

        if only_active:
            stmt = stmt.where(LoanModel.status.not_in(self.TERMINAL_STATUSES))

        if cursor_values is not None:
            borrowed_at = _cursor_datetime(cursor_values[0])
            loan_id = str(cursor_values[1])
            stmt = stmt.where(
                or_(
                    LoanModel.borrowed_at < borrowed_at,
                    and_(
                        LoanModel.borrowed_at == borrowed_at,
                        LoanModel.id > loan_id,
                    ),
                )
            )

        stmt = (
            stmt.order_by(LoanModel.borrowed_at.desc(), LoanModel.id)
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
                [items[-1].borrowed_at, items[-1].id],
                backend="postgresql",
            )
        return QueryPage(items=items, next_cursor=next_cursor)

    async def _find_overdue_from_db(self, limit: int = 100) -> List[LoanReadModel]:
        """PostgreSQL fallback for find_overdue."""
        stmt = (
            select(LoanModel)
            .where(LoanModel.status.not_in(self.TERMINAL_STATUSES))
            .where(LoanModel.due_date < func.now())
            .order_by(LoanModel.due_date, LoanModel.id)
            .limit(limit)
        )

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            return [self._to_read_model_from_db(row) for row in result.scalars().all()]

    def _build_es_query(
        self,
        patron_id: Optional[str] = None,
        only_active: bool = False,
    ) -> dict[str, Any]:
        """Build Elasticsearch query from filter parameters."""
        filter_clauses: list[dict[str, Any]] = []

        if patron_id:
            filter_clauses.append({"term": {"patron_id": patron_id}})

        if filter_clauses or only_active:
            query: dict[str, Any] = {"bool": {"filter": filter_clauses}}
            if only_active:
                # "Active" at the API boundary means outstanding, including a
                # loan already marked overdue/lost; only terminal states are out.
                query["bool"]["must_not"] = [
                    {"terms": {"status": list(self.TERMINAL_STATUSES)}}
                ]
            return query
        return {"match_all": {}}

    def _to_read_model_from_db(self, loan: LoanModel) -> LoanReadModel:
        """Convert database row to read model."""
        return LoanReadModel(
            id=loan.id,
            patron_id=loan.patron_id,
            patron_email=loan.patron_email,
            catalog_book_id=loan.catalog_book_id,
            book_title=loan.book_title,
            borrowed_at=loan.borrowed_at,
            due_date=loan.due_date,
            returned_at=loan.returned_at,
            status=loan.status,
        )

    def _to_read_model_from_es(self, hit: dict[str, Any]) -> LoanReadModel:
        """Convert Elasticsearch hit to read model."""
        return LoanReadModel.from_mapping(hit)


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

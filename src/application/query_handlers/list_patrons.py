"""
List Patrons Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from src.domain.shared_kernel import Logger
    from src.infrastructure.adapters.patron import PatronQueryRepository


@dataclass(frozen=True)
class PatronReadModel:
    """Read model for Patron."""
    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    membership_tier: str
    is_suspended: bool
    suspended_reason: Optional[str]
    registered_at: datetime


@dataclass(frozen=True)
class ListPatronsQuery:
    """Query to list patrons with filters."""
    only_suspended: bool = False
    membership_tier: Optional[str] = None
    limit: int = 100
    offset: int = 0


class ListPatronsHandler:
    """Handles listing patrons."""

    def __init__(self, query_repository: PatronQueryRepository, logger: Logger):
        self.query_repository = query_repository
        self.logger = logger

    async def handle(self, query: ListPatronsQuery) -> List[PatronReadModel]:
        results = await self.query_repository.find_all(
            only_suspended=query.only_suspended,
            membership_tier=query.membership_tier,
            limit=query.limit,
            offset=query.offset,
        )
        return [PatronReadModel(**r) for r in results]

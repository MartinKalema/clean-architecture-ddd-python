"""
Get Patron Query Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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
class GetPatronQuery:
    """Query to get a patron by ID."""
    patron_id: str


class GetPatronHandler:
    """Handles getting a single patron."""

    def __init__(self, query_repository: PatronQueryRepository, logger: Logger):
        self.query_repository = query_repository
        self.logger = logger

    async def handle(self, query: GetPatronQuery) -> Optional[PatronReadModel]:
        result = await self.query_repository.find_by_id(query.patron_id)
        if not result:
            return None
        return PatronReadModel(**result)

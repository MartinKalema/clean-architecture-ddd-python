"""
Patron Query Repository Interface - CQRS Read Side.
"""
from __future__ import annotations

from typing import List, Optional, Protocol


class IPatronQueryRepository(Protocol):
    """Query repository interface for patron (CQRS read side)."""

    async def find_by_id(self, patron_id: str) -> Optional[dict]:
        """Find a patron by ID."""
        ...

    async def find_by_email(self, email: str) -> Optional[dict]:
        """Find a patron by email."""
        ...

    async def find_all(
        self,
        only_suspended: bool = False,
        membership_tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Find patrons with optional filters."""
        ...

    async def count(self, only_suspended: bool = False) -> int:
        """Count patrons matching criteria."""
        ...

"""
Loan Query Repository Interface - CQRS Read Side.
"""
from __future__ import annotations

from typing import List, Optional, Protocol


class ILoanQueryRepository(Protocol):
    """Query repository interface for loans (CQRS read side)."""

    async def find_by_id(self, loan_id: str) -> Optional[dict]:
        """Find a loan by ID."""
        ...

    async def find_by_patron(
        self,
        patron_id: str,
        only_active: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        """Find loans for a patron."""
        ...

    async def find_overdue(self, limit: int = 100) -> List[dict]:
        """Find overdue loans."""
        ...

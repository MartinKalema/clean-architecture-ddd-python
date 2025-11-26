"""
Repository interface for Loan aggregates.
"""
from typing import List, Optional, Protocol

from src.domain.lending.entities import Loan


class LoanRepository(Protocol):
    """Repository for Loan aggregates."""

    async def add(self, loan: Loan) -> Loan:
        """Create a new loan."""
        ...

    async def get_by_id(self, loan_id: str) -> Optional[Loan]:
        """Find a loan by ID."""
        ...

    async def get_active_loans_for_patron(self, patron_id: str) -> List[Loan]:
        """Get all active loans for a patron."""
        ...

    async def get_active_loan_for_book(self, catalog_book_id: str) -> Optional[Loan]:
        """Get the active loan for a specific book."""
        ...

    async def get_overdue_loans(self) -> List[Loan]:
        """Get all overdue loans (for batch processing)."""
        ...

    async def update(self, loan: Loan) -> None:
        """Update a loan."""
        ...

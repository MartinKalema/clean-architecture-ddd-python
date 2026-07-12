"""
Command Repository interface for the Lending bounded context.
"""
from typing import List, Optional, Protocol

from src.domain.lending.entities import Loan


class ILoanCommandRepository(Protocol):
    """Command repository interface for Loan aggregates."""

    async def add(self, loan: Loan) -> Loan:
        """Create a new loan."""
        ...

    async def get_by_id(self, loan_id: str) -> Optional[Loan]:
        """Find a loan by ID."""
        ...

    async def get_by_reservation_id(self, reservation_id: str) -> Optional[Loan]:
        """Find the one loan created for a reservation, if it exists."""
        ...

    async def get_active_loans_for_patron(self, patron_id: str) -> List[Loan]:
        """Get all outstanding loans (active, overdue, or lost) for a patron."""
        ...

    async def get_active_loan_for_book(self, catalog_book_id: str) -> Optional[Loan]:
        """Get the outstanding loan for a book, if any."""
        ...

    async def count_outstanding_for_patron(self, patron_id: str) -> int:
        """Count non-terminal loans for a patron."""
        ...

    async def update(self, loan: Loan) -> None:
        """Update a loan."""
        ...

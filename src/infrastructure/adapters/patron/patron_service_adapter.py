from typing import Optional

from src.domain.lending.interfaces.patron_service import BorrowerInfo
from src.infrastructure.adapters.repositories.patron_query_repository import PatronQueryRepository
from src.infrastructure.adapters.repositories.unit_of_work import UnitOfWork


class PatronServiceAdapter:
    """
    Implementation of the PatronService interface.
    
    This adapter bridges the Lending context to the Patron context.
    It uses CQRS repositories via UnitOfWork for writes and QueryRepo for reads.
    """

    def __init__(
        self, 
        uow: UnitOfWork,
        query_repository: PatronQueryRepository
    ):
        self.uow = uow
        self.query_repository = query_repository

    async def get_borrower_info(self, patron_id: str) -> Optional[BorrowerInfo]:
        """Fetch patron via Query Repo."""
        return await self.query_repository.get_borrower_info(patron_id)

    async def get_borrower_by_email(self, email: str) -> Optional[BorrowerInfo]:
        """Fetch patron by email via Query Repo."""
        return await self.query_repository.get_borrower_by_email(email)

    async def can_patron_borrow(self, patron_id: str) -> bool:
        """Check availability via Command Repo (Consistency)."""
        async with self.uow as uow:
            patron = await uow.patrons.get_by_id(patron_id)
            if not patron:
                return False
            return patron.can_borrow()

    async def increment_loan_count(self, patron_id: str) -> None:
        async with self.uow as uow:
            patron = await uow.patrons.get_by_id(patron_id)
            if patron:
                patron.increment_active_loans()
                await uow.patrons.save(patron)
                await uow.commit()

    async def decrement_loan_count(self, patron_id: str) -> None:
        async with self.uow as uow:
            patron = await uow.patrons.get_by_id(patron_id)
            if patron:
                patron.decrement_active_loans()
                await uow.patrons.save(patron)
                await uow.commit()

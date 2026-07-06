"""
Create Loan Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.domain.lending import Loan
from src.domain.lending.exceptions import BookNotAvailableException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.domain.lending import ILoanUnitOfWork


@dataclass(frozen=True)
class CreateLoanCommand:
    """Command to create a new loan."""
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    loan_duration_days: int = 14
    # When the loan reacts to a borrow that already happened (event-driven
    # flow), the borrow time comes from the event, not this handler's clock
    borrowed_at: Optional[datetime] = None


@dataclass(frozen=True)
class CreateLoanResult:
    """Result of creating a loan."""
    id: str
    patron_id: str
    catalog_book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime


class CreateLoanHandler:
    """Handles loan creation."""

    def __init__(self, uow: ILoanUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: CreateLoanCommand) -> CreateLoanResult:
        async with self.uow:
            existing_loan = await self.uow.loans.get_active_loan_for_book(command.catalog_book_id)
            if existing_loan:
                raise BookNotAvailableException(command.catalog_book_id)

            loan = Loan.create(
                patron_id=command.patron_id,
                patron_email=command.patron_email,
                catalog_book_id=command.catalog_book_id,
                book_title=command.book_title,
                loan_duration_days=command.loan_duration_days,
                borrowed_at=command.borrowed_at or datetime.now(),
            )

            await self.uow.loans.add(loan)
            await self.uow.commit()

            self.logger.info(f"Loan created: {loan.id.value}")

            return CreateLoanResult(
                id=loan.id.value,
                patron_id=loan.patron_id,
                catalog_book_id=loan.catalog_book_id,
                book_title=loan.book_title,
                borrowed_at=loan.borrowed_at,
                due_date=loan.due_date.value,
            )

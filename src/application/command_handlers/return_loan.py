"""
Return Loan Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.lending.exceptions import LoanNotFoundException

if TYPE_CHECKING:
    from src.domain.shared_kernel import Logger
    from src.infrastructure.adapters.lending import LoanUnitOfWork


@dataclass(frozen=True)
class ReturnLoanCommand:
    """Command to return a loan."""
    loan_id: str


@dataclass(frozen=True)
class ReturnLoanResult:
    """Result of returning a loan."""
    id: str
    returned_at: datetime
    was_overdue: bool


class ReturnLoanHandler:
    """Handles loan returns."""

    def __init__(self, uow: LoanUnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: ReturnLoanCommand) -> ReturnLoanResult:
        async with self.uow:
            loan = await self.uow.loans.get_by_id(command.loan_id)
            if not loan:
                raise LoanNotFoundException(command.loan_id)

            returned_at = datetime.now()
            was_overdue = loan.due_date.is_overdue_as_of(returned_at)
            loan.return_book(returned_at)

            await self.uow.loans.update(loan)
            await self.uow.commit()

            self.logger.info(f"Loan returned: {loan.id.value}")

            return ReturnLoanResult(
                id=loan.id.value,
                returned_at=loan.returned_at,
                was_overdue=was_overdue,
            )

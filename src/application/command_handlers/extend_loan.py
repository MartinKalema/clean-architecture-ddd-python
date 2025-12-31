"""
Extend Loan Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.lending.exceptions import LoanNotFoundException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger
    from src.infrastructure.adapters.lending import LoanUnitOfWork


@dataclass(frozen=True)
class ExtendLoanCommand:
    """Command to extend a loan."""
    loan_id: str
    days: int = 7


@dataclass(frozen=True)
class ExtendLoanResult:
    """Result of extending a loan."""
    id: str
    new_due_date: datetime


class ExtendLoanHandler:
    """Handles loan extensions."""

    def __init__(self, uow: LoanUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: ExtendLoanCommand) -> ExtendLoanResult:
        async with self.uow:
            loan = await self.uow.loans.get_by_id(command.loan_id)
            if not loan:
                raise LoanNotFoundException(command.loan_id)

            loan.extend(command.days, datetime.now())

            await self.uow.loans.update(loan)
            await self.uow.commit()

            self.logger.info(f"Loan extended: {loan.id.value} by {command.days} days")

            return ExtendLoanResult(
                id=loan.id.value,
                new_due_date=loan.due_date.value,
            )

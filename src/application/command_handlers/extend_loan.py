"""
Extend Loan Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.lending.exceptions import LoanNotFoundException
from src.application.ports import (
    CommandReceipt,
    IdempotencyKey,
    command_fingerprint,
    require_matching_receipt,
)

if TYPE_CHECKING:
    from src.application.ports import IClock, ILendingApplicationUnitOfWork, ILogger


@dataclass(frozen=True)
class ExtendLoanCommand:
    """Command to extend a loan."""
    loan_id: str
    days: int = 7
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ExtendLoanResult:
    """Result of extending a loan."""
    id: str
    new_due_date: datetime


class ExtendLoanHandler:
    """Handles loan extensions."""

    def __init__(
        self, uow: ILendingApplicationUnitOfWork, logger: ILogger, clock: IClock
    ):
        self.uow = uow
        self.logger = logger
        self.clock = clock

    async def handle(self, command: ExtendLoanCommand) -> ExtendLoanResult:
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        request_hash = command_fingerprint(
            {"loan_id": command.loan_id.strip(), "days": command.days}
        )
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "lending.extend_loan", key.value
                )
                if receipt:
                    response = require_matching_receipt(receipt, request_hash)
                    return ExtendLoanResult(
                        id=str(response["id"]),
                        new_due_date=datetime.fromisoformat(
                            str(response["new_due_date"])
                        ),
                    )

            loan = await self.uow.loans.get_by_id(command.loan_id)
            if not loan:
                raise LoanNotFoundException(command.loan_id)

            loan.extend(command.days, self.clock.now())

            await self.uow.loans.update(loan)
            result = ExtendLoanResult(
                id=loan.id.value,
                new_due_date=loan.due_date.value,
            )
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="lending.extend_loan",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response={
                            "id": result.id,
                            "new_due_date": result.new_due_date.isoformat(),
                        },
                    )
                )
            await self.uow.commit()

            self.logger.info(f"Loan extended: {loan.id.value} by {command.days} days")

            return result

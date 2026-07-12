"""
Return Loan Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.application.ports import (
    CommandReceipt,
    IdempotencyKey,
    command_fingerprint,
    require_matching_receipt,
)
from src.domain.lending.exceptions import LoanNotFoundException

if TYPE_CHECKING:
    from src.application.ports import IClock, ILendingApplicationUnitOfWork, ILogger


@dataclass(frozen=True)
class ReturnLoanCommand:
    """Command to return a loan."""
    loan_id: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ReturnLoanResult:
    """Result of returning a loan."""
    id: str
    returned_at: datetime
    was_overdue: bool


class ReturnLoanHandler:
    """Handles loan returns."""

    def __init__(
        self,
        uow: ILendingApplicationUnitOfWork,
        logger: ILogger,
        clock: IClock,
    ):
        self.uow = uow
        self.logger = logger
        self.clock = clock

    async def handle(self, command: ReturnLoanCommand) -> ReturnLoanResult:
        loan_id = command.loan_id.strip()
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        request_hash = command_fingerprint({"loan_id": loan_id})
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "lending.return_loan", key.value
                )
                if receipt:
                    response = require_matching_receipt(receipt, request_hash)
                    return ReturnLoanResult(
                        id=str(response["id"]),
                        returned_at=datetime.fromisoformat(
                            str(response["returned_at"])
                        ),
                        was_overdue=bool(response["was_overdue"]),
                    )

            loan = await self.uow.loans.get_by_id(loan_id)
            if not loan:
                raise LoanNotFoundException(loan_id)

            changed = loan.return_book(self.clock.now())
            assert loan.returned_at is not None
            was_overdue = loan.due_date.is_overdue_as_of(loan.returned_at)

            if changed:
                await self.uow.loans.update(loan)
            result = ReturnLoanResult(
                id=loan.id.value,
                returned_at=loan.returned_at,
                was_overdue=was_overdue,
            )
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="lending.return_loan",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response={
                            "id": result.id,
                            "returned_at": result.returned_at.isoformat(),
                            "was_overdue": result.was_overdue,
                        },
                    )
                )
            if changed or key:
                await self.uow.commit()

            self.logger.info(f"Loan returned: {loan.id.value}")

            return result

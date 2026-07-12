"""Cancel Loan Command Handler.

Cancellation is the Lending-side compensation for a catalog reservation
that was released before the borrow became definitive.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.lending import (
    LoanNotActiveException,
    ReservationCorrelationMismatchException,
    ReservationId,
)

if TYPE_CHECKING:
    from src.application.ports import ILendingApplicationUnitOfWork, ILogger


@dataclass(frozen=True)
class CancelLoanCommand:
    """Cancel the loan created for one exact catalog reservation."""

    reservation_id: str
    reservation_generation: int
    patron_id: str
    catalog_book_id: str
    # CatalogBookReleased is emitted while Catalog is still RESERVED and has
    # not learned a loan id. Loan-originated compensation must provide one.
    expected_loan_id: str | None
    reason: str


class CancelLoanHandler:
    """Cancels only the loan correlated to the released reservation."""

    def __init__(self, uow: ILendingApplicationUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: CancelLoanCommand) -> bool:
        reservation_id = ReservationId(command.reservation_id).value
        async with self.uow:
            loan = await self.uow.loans.get_by_reservation_id(
                reservation_id
            )
            if loan is None:
                # A reservation can be rejected before a loan is created.
                # Redelivery of the release remains a safe no-op.
                self.logger.info(
                    f"No loan exists for released reservation "
                    f"{reservation_id}"
                )
                return False

            if (
                loan.reservation_id.value != reservation_id
                or loan.reservation_generation != command.reservation_generation
                or loan.patron_id != command.patron_id
                or loan.catalog_book_id != command.catalog_book_id
                or (
                    command.expected_loan_id is not None
                    and loan.id.value != command.expected_loan_id
                )
            ):
                raise ReservationCorrelationMismatchException(
                    reservation_id,
                    f"cancellation does not match loan {loan.id.value}",
                )

            try:
                changed = loan.cancel(command.reason)
            except LoanNotActiveException:
                # The exact loan has already reached another terminal state;
                # retrying this old compensation cannot change that outcome.
                self.logger.warning(
                    f"Ignoring release for terminal loan {loan.id.value}"
                )
                return False

            if not changed:
                self.logger.info(f"Loan already cancelled: {loan.id.value}")
                return False

            await self.uow.loans.update(loan)
            await self.uow.commit()
            self.logger.info(
                f"Loan {loan.id.value} cancelled for released reservation "
                f"{reservation_id}"
            )
            return True

"""
Confirm Borrow On Loan Created - Application event handler.

Third step of the borrow saga: the loan exists in the Lending context,
so the catalog settles the book as BORROWED. Only after this step do
downstream consumers see CatalogBookBorrowed — the definitive fact.

An exact duplicate is a no-op. A permanently stale reservation triggers
compensation of its own tentative loan. Concurrency and infrastructure
failures remain unexpected and propagate for retry/dead-lettering.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.command_handlers.confirm_book_borrow import (
    ConfirmBookBorrowCommand,
    ConfirmBookBorrowHandler,
)
from src.application.command_handlers.cancel_loan import (
    CancelLoanCommand,
    CancelLoanHandler,
)
from src.domain.catalog import StaleReservationException

if TYPE_CHECKING:
    from src.application.ports import ILogger
    from src.domain.lending import LoanCreated


class ConfirmBorrowOnLoanCreatedHandler:
    """Settles the catalog book as borrowed once the loan exists."""

    inbox_consumer_name = "catalog.confirm-borrow-on-loan-created.v1"

    def __init__(
        self,
        confirm_book_borrow_handler: ConfirmBookBorrowHandler,
        cancel_loan_handler: CancelLoanHandler,
        logger: ILogger,
    ):
        self.confirm_book_borrow_handler = confirm_book_borrow_handler
        self.cancel_loan_handler = cancel_loan_handler
        self.logger = logger

    async def handle(self, event: LoanCreated) -> None:
        try:
            await self.confirm_book_borrow_handler.handle(
                ConfirmBookBorrowCommand(
                    book_id=event.book_id,
                    reservation_id=event.reservation_id,
                    reservation_generation=event.reservation_generation,
                    patron_id=event.patron_id,
                    loan_id=event.loan_id,
                    borrowed_at=event.borrowed_at,
                    return_due_date=event.due_date,
                )
            )
        except StaleReservationException:
            # A delayed/replayed LoanCreated must never claim a newer
            # reservation. Cancel its own tentative loan and acknowledge the
            # permanently stale event. Cancellation failures still propagate.
            self.logger.warning(
                f"Loan {event.loan_id} targets stale reservation "
                f"{event.reservation_id}; cancelling the tentative loan"
            )
            await self.cancel_loan_handler.handle(
                CancelLoanCommand(
                    reservation_id=event.reservation_id,
                    reservation_generation=event.reservation_generation,
                    patron_id=event.patron_id,
                    catalog_book_id=event.book_id,
                    expected_loan_id=event.loan_id,
                    reason="catalog reservation is no longer current",
                )
            )

"""
Confirm Borrow On Loan Created - Application event handler.

Third step of the borrow saga: the loan exists in the Lending context,
so the catalog's tentative reservation is confirmed into a final borrow
(RESERVED -> BORROWED). Only after this step do downstream consumers see
CatalogBookBorrowed — the definitive fact.

If the book is no longer reserved when this runs (the reservation reaper
released it before the loan event arrived), the system holds a loan for
a book it gave back: that cannot be auto-repaired from here, so it is
escalated. Keep the reaper TTL comfortably above worst-case event
latency to make this window negligible.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.command_handlers.confirm_book_borrow import (
    ConfirmBookBorrowCommand,
    ConfirmBookBorrowHandler,
)
from src.domain.catalog import BookNotReservedException

if TYPE_CHECKING:
    from src.domain.lending import LoanCreated
    from src.domain.shared_kernel import ILogger


class ConfirmBorrowOnLoanCreatedHandler:
    """Confirms the catalog reservation once the loan exists."""

    def __init__(self, confirm_book_borrow_handler: ConfirmBookBorrowHandler, logger: ILogger):
        self.confirm_book_borrow_handler = confirm_book_borrow_handler
        self.logger = logger

    async def handle(self, event: LoanCreated) -> None:
        try:
            await self.confirm_book_borrow_handler.handle(
                ConfirmBookBorrowCommand(
                    book_id=event.book_id,
                    borrower_email=event.patron_email,
                )
            )
        except BookNotReservedException as e:
            self.logger.error(
                f"SAGA INCONSISTENCY: loan {event.loan_id} exists but book "
                f"{event.book_id} is not reserved ({e}); the reservation "
                f"likely expired before this event arrived — manual "
                f"intervention required"
            )

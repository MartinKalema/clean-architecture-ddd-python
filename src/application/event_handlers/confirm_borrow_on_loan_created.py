"""
Confirm Borrow On Loan Created - Application event handler.

Third step of the borrow saga: the loan exists in the Lending context,
so the catalog settles the book as BORROWED. Only after this step do
downstream consumers see CatalogBookBorrowed — the definitive fact.

The command handler covers every state the book can be in (reserved,
already borrowed, or unreserved — see ConfirmBookBorrowHandler), so any
exception reaching this handler is unexpected and propagates for
retry/dead-lettering.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.command_handlers.confirm_book_borrow import (
    ConfirmBookBorrowCommand,
    ConfirmBookBorrowHandler,
)

if TYPE_CHECKING:
    from src.domain.lending import LoanCreated
    from src.domain.shared_kernel import ILogger


class ConfirmBorrowOnLoanCreatedHandler:
    """Settles the catalog book as borrowed once the loan exists."""

    def __init__(self, confirm_book_borrow_handler: ConfirmBookBorrowHandler, logger: ILogger):
        self.confirm_book_borrow_handler = confirm_book_borrow_handler
        self.logger = logger

    async def handle(self, event: LoanCreated) -> None:
        await self.confirm_book_borrow_handler.handle(
            ConfirmBookBorrowCommand(
                book_id=event.book_id,
                borrower_email=event.patron_email,
                borrowed_at=event.borrowed_at,
                return_due_date=event.due_date,
            )
        )

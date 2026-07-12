"""Reconcile Catalog when the authoritative Lending loan is returned."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.command_handlers.return_book import (
    ReturnBookCommand,
    ReturnBookHandler,
)
from src.domain.catalog import StaleLoanCompletionException

if TYPE_CHECKING:
    from src.application.ports import ILogger
    from src.domain.lending import LoanCompleted


class ReturnBookOnLoanCompletedHandler:
    """Returns a catalog book only for its exact current loan."""

    inbox_consumer_name = "catalog.return-book-on-loan-completed.v1"

    def __init__(self, return_book_handler: ReturnBookHandler, logger: ILogger):
        self.return_book_handler = return_book_handler
        self.logger = logger

    async def handle(self, event: LoanCompleted) -> None:
        try:
            await self.return_book_handler.handle(
                ReturnBookCommand(
                    book_id=event.book_id,
                    loan_id=event.loan_id,
                    reservation_id=event.reservation_id,
                    reservation_generation=event.reservation_generation,
                    patron_id=event.patron_id,
                )
            )
        except StaleLoanCompletionException:
            # A duplicate old completion may arrive after the book has entered
            # a newer workflow. The aggregate rejected it before mutation.
            self.logger.warning(
                f"Ignoring stale completion for loan {event.loan_id} and "
                f"book {event.book_id}"
            )

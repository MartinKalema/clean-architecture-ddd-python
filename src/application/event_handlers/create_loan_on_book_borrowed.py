"""
Create Loan On Book Borrowed - Application event handler.

Completes the borrow feature across bounded contexts: when the Catalog
context commits a borrow (CatalogBookBorrowed), this handler creates the
corresponding loan in the Lending context, in its own transaction. The
client makes one call (POST /books/{id}/borrow); the loan follows by
choreography instead of the caller orchestrating both contexts by hand.

Compensation: the borrow has already committed by the time this runs, so
a rejected loan (unknown patron, suspended patron, creation failure)
cannot roll it back — the handler compensates by returning the book,
restoring availability. A failed compensation is escalated in the logs:
there is nothing left to compensate a compensation with.

Idempotency: delivery is at-least-once. A redelivered event finds an
active loan already exists for the book and is treated as success, not a
reason to compensate.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.command_handlers.create_loan import (
    CreateLoanCommand,
    CreateLoanHandler,
)
from src.application.command_handlers.return_book import (
    ReturnBookCommand,
    ReturnBookHandler,
)
from src.domain.lending.exceptions import BookNotAvailableException

if TYPE_CHECKING:
    from src.domain.catalog import CatalogBookBorrowed
    from src.domain.patron.interfaces.patron_query_repository import (
        IPatronQueryRepository,
    )
    from src.domain.shared_kernel import ILogger


class CreateLoanOnBookBorrowedHandler:
    """Creates a loan in the Lending context when a catalog book is borrowed."""

    def __init__(
        self,
        create_loan_handler: CreateLoanHandler,
        return_book_handler: ReturnBookHandler,
        patron_query_repository: IPatronQueryRepository,
        logger: ILogger,
    ):
        self.create_loan_handler = create_loan_handler
        self.return_book_handler = return_book_handler
        self.patron_query_repository = patron_query_repository
        self.logger = logger

    async def handle(self, event: CatalogBookBorrowed) -> None:
        patron = await self.patron_query_repository.find_by_email(event.borrower_email)
        if patron is None:
            await self._compensate(
                event, f"no patron registered with email {event.borrower_email}"
            )
            return
        if patron.get("is_suspended"):
            await self._compensate(event, f"patron {patron['id']} is suspended")
            return

        # The catalog decided the due date; lending honors it instead of
        # recomputing its own
        loan_duration_days = max(1, (event.return_due_date - event.borrowed_at).days)

        command = CreateLoanCommand(
            patron_id=patron["id"],
            patron_email=event.borrower_email,
            catalog_book_id=event.book_id,
            book_title=event.title,
            loan_duration_days=loan_duration_days,
            borrowed_at=event.borrowed_at,
        )

        try:
            result = await self.create_loan_handler.handle(command)
        except BookNotAvailableException:
            # At-least-once redelivery: the loan for this borrow already
            # exists, so this is success, not a reason to compensate
            self.logger.info(
                f"Loan already active for book {event.book_id}; "
                f"treating redelivered {event.event_type} as processed"
            )
            return
        except Exception as e:
            await self._compensate(event, f"loan creation failed: {e}")
            return

        self.logger.info(
            f"Loan {result.id} created for book {event.book_id} "
            f"borrowed by {event.borrower_email}"
        )

    async def _compensate(self, event: CatalogBookBorrowed, reason: str) -> None:
        """Return the book so the committed borrow does not strand it."""
        self.logger.warning(
            f"Rejecting borrow of book {event.book_id} ({reason}); "
            f"compensating by returning the book"
        )
        try:
            await self.return_book_handler.handle(
                ReturnBookCommand(book_id=event.book_id)
            )
        except Exception as e:
            self.logger.error(
                f"COMPENSATION FAILED: book {event.book_id} is marked borrowed "
                f"but has no loan; manual intervention required",
                exception=e,
            )

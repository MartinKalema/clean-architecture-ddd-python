"""
Create Loan On Book Reserved - Application event handler.

Second step of the borrow saga: when the Catalog context reserves a book
(CatalogBookReserved, the semantic lock), this handler creates the
corresponding loan in the Lending context, in its own transaction. The
client makes one call (POST /books/{id}/borrow); the loan follows by
choreography instead of the caller orchestrating both contexts by hand.

Compensation: the reservation has already committed by the time this
runs, so a deterministic business rejection cannot roll it back — the
handler releases that exact reservation. Unexpected failures propagate
for retry; treating infrastructure failure as business rejection would
silently cancel valid borrows.

Idempotency: reservation identity, rather than current book activity, is
the key. A redelivery finds the loan created for that reservation even if
the loan has since reached a terminal state.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.command_handlers.create_loan import (
    CreateLoanCommand,
    CreateLoanResult,
)
from src.application.command_handlers.release_book_reservation import (
    ReleaseBookReservationCommand,
)
from src.domain.catalog import StaleReservationException
from src.domain.lending.exceptions import (
    BookNotAvailableException,
    PatronBorrowingLimitReachedException,
    PatronNotEligibleForLoanException,
)

if TYPE_CHECKING:
    from src.application.ports import ICommandHandler, ILogger
    from src.domain.catalog import CatalogBookReserved


class CreateLoanOnBookReservedHandler:
    """Creates a loan in the Lending context when a catalog book is reserved."""

    inbox_consumer_name = "lending.create-loan-on-catalog-reserved.v1"

    def __init__(
        self,
        create_loan_operation: ICommandHandler[CreateLoanCommand, CreateLoanResult],
        release_book_reservation_operation: ICommandHandler[
            ReleaseBookReservationCommand, bool
        ],
        logger: ILogger,
    ):
        self._create_loan = create_loan_operation
        self._release_book_reservation = release_book_reservation_operation
        self.logger = logger

    async def handle(self, event: CatalogBookReserved) -> None:
        command = CreateLoanCommand(
            reservation_id=event.reservation_id,
            reservation_generation=event.reservation_generation,
            patron_id=event.patron_id,
            patron_email=event.borrower_email,
            catalog_book_id=event.book_id,
            book_title=event.title,
            borrowed_at=event.reserved_at,
        )

        try:
            result = await self._create_loan.handle(command)
        except (
            BookNotAvailableException,
            PatronBorrowingLimitReachedException,
            PatronNotEligibleForLoanException,
        ) as error:
            # A different outstanding loan is a deterministic rejection.
            # Release only this event's reservation; all transient and
            # unexpected failures escape this handler for consumer retry.
            await self._compensate(event, str(error))
            return

        self.logger.info(
            f"Loan {result.id} created for book {event.book_id} "
            f"reserved by {event.borrower_email}"
        )

    async def _compensate(self, event: CatalogBookReserved, reason: str) -> None:
        """Release the reservation so the committed reserve does not strand it."""
        self.logger.warning(
            f"Rejecting borrow of book {event.book_id} ({reason}); "
            f"compensating by releasing the reservation"
        )
        try:
            await self._release_book_reservation.handle(
                ReleaseBookReservationCommand(
                    book_id=event.book_id,
                    reservation_id=event.reservation_id,
                    reservation_generation=event.reservation_generation,
                    patron_id=event.patron_id,
                    reason=reason,
                )
            )
        except StaleReservationException:
            # The reservation was already released/confirmed or superseded.
            # The exact-match aggregate guard guarantees no newer workflow
            # was mutated, so retrying this old compensation is pointless.
            self.logger.warning(
                f"Ignoring stale compensation for reservation "
                f"{event.reservation_id}"
            )
        except Exception as error:
            self.logger.error(
                f"Compensation failed for reservation {event.reservation_id}; "
                f"the state transition will keep retrying, while the reaper "
                f"remains the semantic-lock safety net",
                exception=error,
            )
            raise

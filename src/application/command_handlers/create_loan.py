"""
Create Loan Command Handler.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.lending import (
    ConcurrentLoanCreationException,
    LendingPolicy,
    Loan,
    PatronBorrowingLimitReachedException,
    PatronNotEligibleForLoanException,
    ReservationCorrelationMismatchException,
    ReservationId,
)
from src.domain.lending.exceptions import BookNotAvailableException

if TYPE_CHECKING:
    from src.application.ports import (
        IBorrowerDirectory,
        ILendingApplicationUnitOfWork,
        ILogger,
    )


@dataclass(frozen=True)
class CreateLoanCommand:
    """Command to create a new loan."""
    reservation_id: str
    reservation_generation: int
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    # When the loan reacts to a borrow that already happened (event-driven
    # flow), the borrow time comes from the event, not this handler's clock
    borrowed_at: datetime


@dataclass(frozen=True)
class CreateLoanResult:
    """Result of creating a loan."""
    id: str
    reservation_id: str
    reservation_generation: int
    patron_id: str
    catalog_book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime


class CreateLoanHandler:
    """Handles loan creation."""

    def __init__(
        self,
        uow: ILendingApplicationUnitOfWork,
        borrower_directory: IBorrowerDirectory,
        logger: ILogger,
    ):
        self.uow = uow
        self.borrower_directory = borrower_directory
        self.logger = logger

    async def handle(self, command: CreateLoanCommand) -> CreateLoanResult:
        reservation_id = ReservationId(command.reservation_id).value
        try:
            return await self._create_or_replay(command, reservation_id)
        except ConcurrentLoanCreationException as conflict:
            return await self._reconcile_concurrent_insert(
                command, reservation_id, conflict
            )

    async def _create_or_replay(
        self,
        command: CreateLoanCommand,
        reservation_id: str,
    ) -> CreateLoanResult:
        async with self.uow:
            # Reservation identity is the idempotency key for this workflow.
            # It must be checked before book availability: a replay after the
            # original loan was cancelled/returned must never create a second
            # loan for the same reservation.
            existing_loan = await self.uow.loans.get_by_reservation_id(
                reservation_id
            )
            if existing_loan:
                self._require_exact_replay(
                    command, existing_loan, reservation_id
                )
                self.logger.info(
                    f"Loan already exists for reservation "
                    f"{reservation_id}: {existing_loan.id.value}"
                )
                return self._result(existing_loan)

            # Admission is a named application transaction contract, not a
            # hidden side effect of a repository query. Patron suspension and
            # tier changes acquire the same fence before they mutate policy.
            await self.uow.acquire_borrowing_fence(command.patron_id)
            outstanding_count = (
                await self.uow.loans.count_outstanding_for_patron(
                    command.patron_id
                )
            )

            # The patron advisory lock may have waited behind another
            # transaction. Re-read the idempotency key before applying the
            # limit or book-contention decisions; an exact concurrent replay
            # is success, never a reason to release its reservation.
            existing_loan = await self.uow.loans.get_by_reservation_id(
                reservation_id
            )
            if existing_loan:
                self._require_exact_replay(
                    command, existing_loan, reservation_id
                )
                return self._result(existing_loan)

            # The UoW holds the same transaction-level advisory fence used by
            # Patron suspension and tier changes. This second
            # authoritative ACL read therefore has a deterministic ordering
            # relative to policy mutation.
            borrower = await self.borrower_directory.get_by_id(command.patron_id)
            if borrower is None:
                raise PatronNotEligibleForLoanException(
                    command.patron_id, "patron no longer exists"
                )
            if borrower.patron_id != command.patron_id:
                raise PatronNotEligibleForLoanException(
                    command.patron_id, "authoritative identity mismatch"
                )
            if borrower.email != command.patron_email:
                raise PatronNotEligibleForLoanException(
                    command.patron_id, "authoritative email mismatch"
                )
            if not borrower.is_eligible:
                raise PatronNotEligibleForLoanException(
                    command.patron_id,
                    borrower.ineligible_reason or "patron policy rejected borrowing",
                )

            terms = LendingPolicy.for_membership_tier(
                borrower.membership_tier
            )
            if terms is None:
                raise PatronNotEligibleForLoanException(
                    command.patron_id,
                    "membership tier is not supported by Lending",
                )

            if outstanding_count >= terms.max_outstanding_loans:
                raise PatronBorrowingLimitReachedException(
                    command.patron_id, terms.max_outstanding_loans
                )

            existing_loan = await self.uow.loans.get_active_loan_for_book(command.catalog_book_id)
            if existing_loan:
                raise BookNotAvailableException(command.catalog_book_id)

            loan = Loan.create(
                reservation_id=reservation_id,
                reservation_generation=command.reservation_generation,
                patron_id=command.patron_id,
                patron_email=command.patron_email,
                catalog_book_id=command.catalog_book_id,
                book_title=command.book_title,
                loan_duration_days=terms.loan_duration_days,
                borrowed_at=command.borrowed_at,
            )

            await self.uow.loans.add(loan)
            await self.uow.commit()

            self.logger.info(f"Loan created: {loan.id.value}")

            return self._result(loan)

    async def _reconcile_concurrent_insert(
        self,
        command: CreateLoanCommand,
        reservation_id: str,
        conflict: ConcurrentLoanCreationException,
    ) -> CreateLoanResult:
        """Resolve a uniqueness race without compensating a valid replay."""
        async with self.uow:
            winner = await self.uow.loans.get_by_reservation_id(reservation_id)
            if winner is not None:
                self._require_exact_replay(command, winner, reservation_id)
                self.logger.info(
                    f"Concurrent replay resolved to loan {winner.id.value} "
                    f"for reservation {reservation_id}"
                )
                return self._result(winner)

            winner = await self.uow.loans.get_active_loan_for_book(
                command.catalog_book_id
            )
            if winner is not None:
                raise BookNotAvailableException(command.catalog_book_id) from conflict

        # A winner may not yet be visible, or the database reported a
        # different transient integrity failure. Let message retry policy
        # re-run the identity check; never compensate an ambiguous race.
        raise conflict

    @staticmethod
    def _result(loan: Loan) -> CreateLoanResult:
        return CreateLoanResult(
            id=loan.id.value,
            reservation_id=loan.reservation_id.value,
            reservation_generation=loan.reservation_generation,
            patron_id=loan.patron_id,
            catalog_book_id=loan.catalog_book_id,
            book_title=loan.book_title,
            borrowed_at=loan.borrowed_at,
            due_date=loan.due_date.value,
        )

    @staticmethod
    def _require_exact_replay(
        command: CreateLoanCommand,
        loan: Loan,
        reservation_id: str,
    ) -> None:
        """Reject token reuse with facts that differ from the original loan."""
        comparisons = {
            "reservation_id": (
                loan.reservation_id.value,
                reservation_id,
            ),
            "reservation_generation": (
                loan.reservation_generation,
                command.reservation_generation,
            ),
            "patron_id": (loan.patron_id, command.patron_id),
            "patron_email": (loan.patron_email, command.patron_email),
            "catalog_book_id": (
                loan.catalog_book_id,
                command.catalog_book_id,
            ),
            "book_title": (loan.book_title, command.book_title),
            "borrowed_at": (loan.borrowed_at, command.borrowed_at),
        }
        mismatches = [
            field
            for field, (actual, expected) in comparisons.items()
            if actual != expected
        ]
        if mismatches:
            raise ReservationCorrelationMismatchException(
                reservation_id,
                f"immutable field(s) differ: {', '.join(mismatches)}",
            )

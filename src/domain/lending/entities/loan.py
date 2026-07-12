"""
Loan Aggregate Root - The core aggregate of the Lending context.

A Loan represents the borrowing of a book by a patron. It's the heart of
the library's lending operations.
"""
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Optional

from src.domain.lending.events.lending_events import (
    BookOverdue,
    LoanCancelled,
    LoanCompleted,
    LoanCreated,
    LoanExtended,
)
from src.domain.lending.exceptions import (
    CannotExtendOverdueLoanException,
    InvalidCancellationReasonException,
    InvalidLoanDurationException,
    InvalidLoanReferenceException,
    InvalidLoanReturnDateException,
    InvalidLoanStateException,
    InvalidReservationGenerationException,
    LoanNotActiveException,
    LoanNotOverdueException,
)
from src.domain.lending.value_objects import DueDate, LoanId, LoanStatus, ReservationId
from src.domain.shared_kernel import (
    AggregateRoot,
    EmailAddress,
    aggregate_transition,
    require_utc_datetime,
)


@dataclass
class Loan(AggregateRoot):
    """
    A book loan - the core aggregate of the Lending context.

    Invariants:
    - A loan must have a valid patron and book reference
    - A loan cannot be returned before it's borrowed
    - A loan can only be extended if it's active and not overdue
    """

    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    due_date: DueDate
    borrowed_at: datetime
    reservation_id: ReservationId
    reservation_generation: int
    id: LoanId = field(default_factory=LoanId.next_id)
    status: LoanStatus = LoanStatus.ACTIVE
    returned_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, LoanId):
            self.id = LoanId(self.id)
        if not isinstance(self.reservation_id, ReservationId):
            self.reservation_id = ReservationId(self.reservation_id)
        if not isinstance(self.due_date, DueDate):
            self.due_date = DueDate(self.due_date)
        try:
            if not isinstance(self.status, LoanStatus):
                self.status = LoanStatus(self.status)
        except (TypeError, ValueError) as error:
            raise InvalidLoanStateException("unknown status") from error
        self.patron_id = self._normalize_reference(self.patron_id, "patron_id")
        self.catalog_book_id = self._normalize_reference(
            self.catalog_book_id, "catalog_book_id"
        )
        self.patron_email = EmailAddress(self.patron_email).value
        self.book_title = " ".join(str(self.book_title).split())
        if not self.book_title or len(self.book_title) > 100:
            raise InvalidLoanReferenceException("book_title")
        if self.reservation_generation < 1:
            raise InvalidReservationGenerationException(self.reservation_generation)
        self.borrowed_at = require_utc_datetime(self.borrowed_at, "borrowed_at")
        if self.returned_at is not None:
            self.returned_at = require_utc_datetime(
                self.returned_at, "returned_at"
            )
        if self.due_date.value <= self.borrowed_at:
            raise InvalidLoanDurationException(0)
        if self.returned_at is not None and self.returned_at < self.borrowed_at:
            raise InvalidLoanReturnDateException(self.id.value)
        if (self.status is LoanStatus.RETURNED) != (self.returned_at is not None):
            raise InvalidLoanStateException(
                "returned status and returned_at must change together"
            )
        super().__post_init__()

    @staticmethod
    def _normalize_reference(value: str, field: str) -> str:
        normalized = str(value).strip()
        if (
            not normalized
            or len(normalized) > 64
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", normalized)
        ):
            raise InvalidLoanReferenceException(field)
        return normalized

    @classmethod
    def create(
        cls,
        patron_id: str,
        patron_email: str,
        catalog_book_id: str,
        book_title: str,
        loan_duration_days: int,
        borrowed_at: datetime,
        reservation_id: str | ReservationId,
        reservation_generation: int,
    ) -> "Loan":
        """Factory method to create a new loan."""
        if reservation_generation < 1:
            raise InvalidReservationGenerationException(reservation_generation)
        token = (
            reservation_id
            if isinstance(reservation_id, ReservationId)
            else ReservationId(reservation_id)
        )
        due_date = DueDate.from_loan_duration(borrowed_at, loan_duration_days)

        loan = cls(
            patron_id=patron_id,
            patron_email=patron_email,
            catalog_book_id=catalog_book_id,
            book_title=book_title,
            due_date=due_date,
            borrowed_at=borrowed_at,
            reservation_id=token,
            reservation_generation=reservation_generation,
        )

        loan.add_event(
            LoanCreated(
                loan_id=loan.id.value,
                reservation_id=token.value,
                reservation_generation=reservation_generation,
                patron_id=patron_id,
                patron_email=patron_email,
                book_id=catalog_book_id,
                book_title=book_title,
                borrowed_at=borrowed_at,
                due_date=due_date.value,
            )
        )

        return loan

    @aggregate_transition
    def return_book(self, returned_at: datetime) -> bool:
        """Mark the loan as returned."""
        if self.status == LoanStatus.RETURNED:
            return False
        if self.status == LoanStatus.CANCELLED:
            raise LoanNotActiveException(self.id.value, "return")
        returned_at = require_utc_datetime(returned_at, "returned_at")
        if returned_at < self.borrowed_at:
            raise InvalidLoanReturnDateException(self.id.value)

        self.status = LoanStatus.RETURNED
        self.returned_at = returned_at

        self.add_event(
            LoanCompleted(
                loan_id=self.id.value,
                reservation_id=self.reservation_id.value,
                reservation_generation=self.reservation_generation,
                patron_id=self.patron_id,
                book_id=self.catalog_book_id,
                returned_at=self.returned_at,
                was_overdue=self.due_date.is_overdue_as_of(returned_at),
            )
        )
        return True

    @aggregate_transition
    def cancel(self, reason: str) -> bool:
        """Compensate a loan whose exact Catalog reservation was not confirmed."""
        if self.status == LoanStatus.CANCELLED:
            return False
        if self.status == LoanStatus.RETURNED:
            raise LoanNotActiveException(self.id.value, "cancel")
        reason = " ".join(str(reason).split())
        if not reason or len(reason) > 500:
            raise InvalidCancellationReasonException()

        self.status = LoanStatus.CANCELLED
        self.add_event(
            LoanCancelled(
                loan_id=self.id.value,
                reservation_id=self.reservation_id.value,
                reservation_generation=self.reservation_generation,
                patron_id=self.patron_id,
                book_id=self.catalog_book_id,
                reason=reason,
            )
        )
        return True

    @aggregate_transition
    def mark_overdue(self, current_time: datetime) -> None:
        """Mark the loan as overdue (called by a scheduled job)."""
        if self.status != LoanStatus.ACTIVE:
            raise LoanNotActiveException(self.id.value, "mark as overdue")
        if not self.due_date.is_overdue_as_of(current_time):
            raise LoanNotOverdueException(self.id.value)

        self.status = LoanStatus.OVERDUE

        self.add_event(
            BookOverdue(
                loan_id=self.id.value,
                patron_id=self.patron_id,
                patron_email=self.patron_email,
                book_id=self.catalog_book_id,
                book_title=self.book_title,
                due_date=self.due_date.value,
                days_overdue=abs(self.due_date.days_until_due_as_of(current_time)),
            )
        )

    @aggregate_transition
    def extend(self, days: int, current_time: datetime) -> None:
        """Extend the loan by a number of days."""
        if self.status != LoanStatus.ACTIVE:
            raise LoanNotActiveException(self.id.value, "extend")
        if self.due_date.is_overdue_as_of(current_time):
            raise CannotExtendOverdueLoanException(self.id.value)

        old_due_date = self.due_date
        self.due_date = self.due_date.extend(days)

        self.add_event(
            LoanExtended(
                loan_id=self.id.value,
                patron_id=self.patron_id,
                book_id=self.catalog_book_id,
                old_due_date=old_due_date.value,
                new_due_date=self.due_date.value,
            )
        )

    def is_overdue_as_of(self, current_time: datetime) -> bool:
        """Check if the loan is overdue as of the given time."""
        return self.status == LoanStatus.ACTIVE and self.due_date.is_overdue_as_of(current_time)

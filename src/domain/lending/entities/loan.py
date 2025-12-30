"""
Loan Aggregate Root - The core aggregate of the Lending context.

A Loan represents the borrowing of a book by a patron. It's the heart of
the library's lending operations.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.domain.lending.events.lending_events import (
    BookOverdue,
    LoanCompleted,
    LoanCreated,
    LoanExtended,
)
from src.domain.lending.exceptions import (
    CannotExtendOverdueLoanException,
    LoanAlreadyReturnedException,
    LoanNotActiveException,
    LoanNotOverdueException,
)
from src.domain.lending.value_objects import DueDate, LoanId, LoanStatus
from src.domain.shared_kernel import AggregateRoot


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
    id: LoanId = field(default_factory=LoanId.next_id)
    status: LoanStatus = LoanStatus.ACTIVE
    returned_at: Optional[datetime] = None

    @classmethod
    def create(
        cls,
        patron_id: str,
        patron_email: str,
        catalog_book_id: str,
        book_title: str,
        loan_duration_days: int,
        borrowed_at: datetime,
    ) -> "Loan":
        """Factory method to create a new loan."""
        due_date = DueDate.from_loan_duration(borrowed_at, loan_duration_days)

        loan = cls(
            patron_id=patron_id,
            patron_email=patron_email,
            catalog_book_id=catalog_book_id,
            book_title=book_title,
            due_date=due_date,
            borrowed_at=borrowed_at,
        )

        loan.add_event(
            LoanCreated(
                loan_id=loan.id.value,
                patron_id=patron_id,
                patron_email=patron_email,
                book_id=catalog_book_id,
                book_title=book_title,
                borrowed_at=borrowed_at,
                due_date=due_date.value,
            )
        )

        return loan

    def return_book(self, returned_at: datetime) -> None:
        """Mark the loan as returned."""
        if self.status == LoanStatus.RETURNED:
            raise LoanAlreadyReturnedException(self.id.value)

        self.status = LoanStatus.RETURNED
        self.returned_at = returned_at

        self.add_event(
            LoanCompleted(
                loan_id=self.id.value,
                patron_id=self.patron_id,
                book_id=self.catalog_book_id,
                returned_at=self.returned_at,
                was_overdue=self.due_date.is_overdue_as_of(returned_at),
            )
        )

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

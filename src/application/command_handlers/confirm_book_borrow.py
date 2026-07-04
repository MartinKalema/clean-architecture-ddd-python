"""
Confirm Book Borrow Command - CQRS Command Side.

Third step of the borrow saga: the loan exists in the Lending context,
so the catalog's book must end up BORROWED. Three cases:

- RESERVED: the normal saga path — confirm the reservation.
- BORROWED: at-least-once redelivery — already done, skip.
- AVAILABLE: the loan arrived without a reservation (direct loan API, or
  the reaper released an expired reservation before the event arrived).
  The book is claimed directly, bringing the catalog back in line with
  the loan instead of stranding a loan for an "available" book.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.catalog import BookNotFoundException, BookStatus

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork
    from src.domain.shared_kernel import ILogger


@dataclass(frozen=True)
class ConfirmBookBorrowCommand:
    """Command to settle a book as borrowed for an existing loan."""
    book_id: str
    borrower_email: str
    borrowed_at: datetime
    return_due_date: datetime


class ConfirmBookBorrowHandler:
    """Handles the ConfirmBookBorrowCommand."""

    def __init__(self, uow: UnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: ConfirmBookBorrowCommand) -> None:
        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                raise BookNotFoundException(command.book_id)

            if book.status == BookStatus.BORROWED:
                # At-least-once redelivery: already confirmed
                self.logger.info(
                    f"Book already confirmed borrowed: {command.book_id}"
                )
                return

            if book.status == BookStatus.RESERVED:
                book.confirm_borrow(command.borrower_email)
            else:
                # Loan without a reservation: direct loan path, or the
                # reservation expired before this event arrived
                self.logger.info(
                    f"Loan exists for unreserved book {command.book_id}; "
                    f"claiming it directly to keep catalog and lending consistent"
                )
                book.mark_borrowed(
                    command.borrower_email,
                    command.borrowed_at,
                    command.return_due_date,
                )

            await self.uow.books.update(book)
            await self.uow.commit()

            self.logger.info(
                f"Borrow confirmed: {book.title.value} ({book.id.value})"
            )

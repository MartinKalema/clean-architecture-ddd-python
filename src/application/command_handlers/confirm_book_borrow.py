"""
Confirm Book Borrow Command - CQRS Command Side.

Third step of the borrow saga: the loan exists in the Lending context,
so the exact catalog reservation is confirmed as BORROWED. The aggregate
owns correlation validation; it never claims an available book or a newer
reservation on behalf of a delayed event.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.application.ports import BorrowOperationStatus
from src.domain.catalog import BookNotFoundException

if TYPE_CHECKING:
    from src.application.ports import ICatalogApplicationUnitOfWork, IClock, ILogger


@dataclass(frozen=True)
class ConfirmBookBorrowCommand:
    """Command to settle a book as borrowed for an existing loan."""
    book_id: str
    reservation_id: str
    reservation_generation: int
    patron_id: str
    loan_id: str
    borrowed_at: datetime
    return_due_date: datetime


class ConfirmBookBorrowHandler:
    """Handles the ConfirmBookBorrowCommand."""

    def __init__(self, uow: ICatalogApplicationUnitOfWork, logger: ILogger, clock: IClock):
        self.uow = uow
        self.logger = logger
        self.clock = clock

    async def handle(self, command: ConfirmBookBorrowCommand) -> bool:
        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                raise BookNotFoundException(command.book_id)

            changed = book.confirm_borrow(
                reservation_id=command.reservation_id,
                reservation_generation=command.reservation_generation,
                patron_id=command.patron_id,
                loan_id=command.loan_id,
                borrowed_at=command.borrowed_at,
                return_due_date=command.return_due_date,
            )

            if not changed:
                self.logger.info(
                    f"Borrow already confirmed for loan {command.loan_id}"
                )
                return False

            await self.uow.books.update(book)
            await self.uow.borrow_operations.transition(
                command.reservation_id,
                BorrowOperationStatus.BORROWED,
                book_id=command.book_id,
                patron_id=command.patron_id,
                reservation_generation=command.reservation_generation,
                loan_id=command.loan_id,
                updated_at=self.clock.now(),
            )
            await self.uow.commit()

            self.logger.info(
                f"Borrow confirmed: {book.title.value} ({book.id.value})"
            )
            return True

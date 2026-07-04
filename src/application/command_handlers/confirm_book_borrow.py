"""
Confirm Book Borrow Command - CQRS Command Side.

Third step of the borrow saga: the loan exists in the Lending context,
so the catalog's reservation is confirmed into a final borrow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.catalog import BookNotFoundException, BookStatus

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork
    from src.domain.shared_kernel import ILogger


@dataclass(frozen=True)
class ConfirmBookBorrowCommand:
    """Command to confirm a reserved book into a borrow."""
    book_id: str
    borrower_email: str


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

            book.confirm_borrow(command.borrower_email)

            await self.uow.books.update(book)
            await self.uow.commit()

            self.logger.info(
                f"Borrow confirmed: {book.title.value} ({book.id.value})"
            )

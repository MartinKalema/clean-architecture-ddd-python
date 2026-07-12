"""
Return Book Command - CQRS Command Side.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.ports import BorrowOperationStatus
from src.domain.catalog import BookNotFoundException

if TYPE_CHECKING:
    from src.application.ports import ICatalogApplicationUnitOfWork, IClock, ILogger


@dataclass(frozen=True)
class ReturnBookCommand:
    """Command to return a borrowed book."""
    book_id: str
    loan_id: str
    reservation_id: str
    reservation_generation: int
    patron_id: str


@dataclass(frozen=True)
class ReturnBookResult:
    """Result of returning a book."""
    id: str
    title: str
    author: str
    is_borrowed: bool
    status: str = "available"


class ReturnBookHandler:
    """
    Handles the ReturnBookCommand.

    Emits BookReturned domain event for read model sync.
    """

    def __init__(self, uow: ICatalogApplicationUnitOfWork, logger: ILogger, clock: IClock):
        self.uow = uow
        self.logger = logger
        self.clock = clock

    async def handle(self, command: ReturnBookCommand) -> ReturnBookResult:
        """Execute the command to return a book."""
        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                self.logger.warning(f"Attempted to return non-existent book: {command.book_id}")
                raise BookNotFoundException(command.book_id)

            changed = book.return_book(
                loan_id=command.loan_id,
                reservation_id=command.reservation_id,
                reservation_generation=command.reservation_generation,
                patron_id=command.patron_id,
            )

            if not changed:
                self.logger.info(
                    f"Catalog return already applied for loan {command.loan_id}"
                )
                return ReturnBookResult(
                    id=book.id.value,
                    title=book.title.value,
                    author=book.author.value,
                    is_borrowed=book.is_borrowed,
                    status=book.status.value,
                )

            await self.uow.books.update(book)
            await self.uow.borrow_operations.transition(
                command.reservation_id,
                BorrowOperationStatus.RETURNED,
                book_id=command.book_id,
                patron_id=command.patron_id,
                reservation_generation=command.reservation_generation,
                loan_id=command.loan_id,
                updated_at=self.clock.now(),
            )
            await self.uow.commit()

            self.logger.info(f"Book returned: {book.title.value} ({book.id.value})")

            return ReturnBookResult(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed,
                status=book.status.value
            )

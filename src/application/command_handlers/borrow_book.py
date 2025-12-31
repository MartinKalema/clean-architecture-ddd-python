"""
Borrow Book Command - CQRS Command Side.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.domain.catalog import BookNotFoundException

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork
    from src.domain.shared_kernel import ILogger


@dataclass(frozen=True)
class BorrowBookCommand:
    """Command to borrow a book."""
    book_id: str
    borrower_email: str


@dataclass(frozen=True)
class BorrowBookResult:
    """Result of borrowing a book."""
    id: str
    title: str
    author: str
    is_borrowed: bool
    return_due_date: Optional[datetime] = None


class BorrowBookHandler:
    """
    Handles the BorrowBookCommand.

    Emits BookBorrowed domain event for read model sync.
    """

    def __init__(self, uow: UnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: BorrowBookCommand) -> BorrowBookResult:
        """Execute the command to borrow a book."""
        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                self.logger.warning(f"Attempted to borrow non-existent book: {command.book_id}")
                raise BookNotFoundException(command.book_id)

            book.borrow(command.borrower_email, datetime.now())

            await self.uow.books.update(book)
            await self.uow.commit()

            self.logger.info(f"Book borrowed: {book.title.value} ({book.id.value})")

            return BorrowBookResult(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed,
                return_due_date=book.return_due_date
            )

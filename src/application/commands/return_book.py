"""
Return Book Command - CQRS Command Side.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.catalog import BookNotFoundException

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork
    from src.domain.shared_kernel import Logger


@dataclass(frozen=True)
class ReturnBookCommand:
    """Command to return a borrowed book."""
    book_id: str


@dataclass(frozen=True)
class ReturnBookResult:
    """Result of returning a book."""
    id: str
    title: str
    author: str
    is_borrowed: bool


class ReturnBookHandler:
    """
    Handles the ReturnBookCommand.

    Emits BookReturned domain event for read model sync.
    """

    def __init__(self, uow: UnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: ReturnBookCommand) -> ReturnBookResult:
        """Execute the command to return a book."""
        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                self.logger.warning(f"Attempted to return non-existent book: {command.book_id}")
                raise BookNotFoundException(command.book_id)

            # Domain logic - emits BookReturned event
            book.return_book()

            await self.uow.books.update(book)
            await self.uow.commit()

            self.logger.info(f"Book returned: {book.title.value} ({book.id.value})")

            return ReturnBookResult(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed
            )

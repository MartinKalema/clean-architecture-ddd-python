"""
Add Book Command - CQRS Command Side.

Commands are immutable data structures that represent intent to change state.
Handlers execute the command and may emit domain events.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.catalog import Author, Book, BookId, Title

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork
    from src.domain.shared_kernel import Logger


@dataclass(frozen=True)
class AddBookCommand:
    """Command to add a new book to the catalog."""
    title: str
    author: str


@dataclass(frozen=True)
class AddBookResult:
    """Result of adding a book."""
    id: str
    title: str
    author: str
    is_borrowed: bool = False


class AddBookHandler:
    """
    Handles the AddBookCommand.

    This is part of the CQRS write side - it modifies state
    and may emit domain events for read model synchronization.
    """

    def __init__(self, uow: UnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: AddBookCommand) -> AddBookResult:
        """Execute the command to add a new book."""
        async with self.uow:
            book = Book(
                id=BookId.next_id(),
                title=Title(command.title),
                author=Author(command.author)
            )

            await self.uow.books.add(book)
            await self.uow.commit()

            self.logger.info(f"Book added: {book.title.value} ({book.id.value})")

            return AddBookResult(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed
            )

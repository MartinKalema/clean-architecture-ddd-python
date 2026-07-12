"""
Add Book Command - CQRS Command Side.

Commands are immutable data structures that represent intent to change state.
Handlers execute the command and may emit domain events.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.catalog import Author, Book, BookId, Title
from src.application.ports import (
    CommandReceipt,
    IdempotencyKey,
    command_fingerprint,
    require_matching_receipt,
)

if TYPE_CHECKING:
    from src.application.ports import ICatalogApplicationUnitOfWork, ILogger


@dataclass(frozen=True)
class AddBookCommand:
    """Command to add a new book to the catalog."""
    title: str
    author: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class AddBookResult:
    """Result of adding a book."""
    id: str
    title: str
    author: str
    is_borrowed: bool = False
    status: str = "available"


class AddBookHandler:
    """
    Handles the AddBookCommand.

    This is part of the CQRS write side - it modifies state
    and may emit domain events for read model synchronization.
    """

    def __init__(self, uow: ICatalogApplicationUnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: AddBookCommand) -> AddBookResult:
        """Execute the command to add a new book."""
        title = Title(command.title)
        author = Author(command.author)
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        request_hash = command_fingerprint(
            {"title": title.value, "author": author.value}
        )
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "catalog.add_book", key.value
                )
                if receipt:
                    return AddBookResult(
                        **require_matching_receipt(receipt, request_hash)
                    )

            book = Book(
                id=BookId.next_id(),
                title=title,
                author=author,
            )

            await self.uow.books.add(book)
            result = AddBookResult(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed,
                status=book.status.value,
            )
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="catalog.add_book",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response=result.__dict__,
                    )
                )
            await self.uow.commit()

            self.logger.info(f"Book added: {book.title.value} ({book.id.value})")

            return result

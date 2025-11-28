from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.catalog import Book, BookId, Title, Author
from src.application.dto.book_dto import AddBookOutputDto

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork
    from src.domain.shared_kernel import Logger
    from src.application.dto.book_dto import AddBookInputDto


class AddBook:
    def __init__(self, uow: UnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def execute(self, input_dto: AddBookInputDto) -> AddBookOutputDto:
        async with self.uow:
            book = Book(
                id=BookId.next_id(),
                title=Title(input_dto.title),
                author=Author(input_dto.author)
            )
            await self.uow.books.add(book)
            await self.uow.commit()

            self.logger.info(f"Book added successfully: {book.title.value} ({book.id.value})")

            return AddBookOutputDto(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed
            )

from typing import List
from src.domain.entities.book import Book
from src.domain.interfaces.unit_of_work import UnitOfWork
from src.application.dto.book_dto import BookOutputDto

class ListBooks:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def execute(self) -> List[BookOutputDto]:
        async with self.uow:
            books = await self.uow.books.get_all()
            return [
                BookOutputDto(
                    id=book.id.value,
                    title=book.title.value,
                    author=book.author.value,
                    is_borrowed=book.is_borrowed
                )
                for book in books
            ]

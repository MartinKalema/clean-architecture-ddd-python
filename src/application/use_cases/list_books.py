from typing import List
from src.domain.interfaces.book_repository import BookRepository
from src.domain.interfaces.unit_of_work import UnitOfWork
from src.application.dto.book_dto import BookOutputDto
from src.domain.interfaces.logger import Logger

class ListBooks:
    def __init__(self, uow: UnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def execute(self) -> List[BookOutputDto]:
        async with self.uow:
            books = await self.uow.books.get_all()
            self.logger.info(f"Listed {len(books)} books")
            return [
                BookOutputDto(
                    id=book.id.value,
                    title=book.title.value,
                    author=book.author.value,
                    is_borrowed=book.is_borrowed
                )
                for book in books
            ]

from typing import List
from src.domain.entities.book import Book
from src.domain.interfaces.book_repository import BookRepository
from src.application.dto.book_dto import BookOutputDto

class ListBooks:
    def __init__(self, repository: BookRepository):
        self.repository = repository

    async def execute(self) -> List[BookOutputDto]:
        books = await self.repository.get_all()
        return [
            BookOutputDto(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed
            )
            for book in books
        ]

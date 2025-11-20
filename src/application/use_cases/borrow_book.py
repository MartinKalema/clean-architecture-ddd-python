from src.domain.entities.book import Book
from src.domain.exceptions.book_exceptions import BookNotFoundException
from src.domain.interfaces.book_repository import BookRepository
from src.application.dto.book_dto import BorrowBookInputDto, BorrowBookOutputDto

class BorrowBook:
    def __init__(self, repository: BookRepository):
        self.repository = repository

    async def execute(self, input_dto: BorrowBookInputDto) -> BorrowBookOutputDto:
        book = await self.repository.get_by_id(input_dto.book_id)
        if not book:
            raise BookNotFoundException(f"Book with ID {input_dto.book_id} not found")
        
        book.borrow()
        
        await self.repository.update(book)
        
        return BorrowBookOutputDto(
            id=book.id.value,
            title=book.title.value,
            author=book.author.value,
            is_borrowed=book.is_borrowed
        )

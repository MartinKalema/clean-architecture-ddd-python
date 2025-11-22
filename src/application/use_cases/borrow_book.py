from src.domain.entities.book import Book
from src.domain.exceptions.book_exceptions import BookNotFoundException
from src.domain.interfaces.unit_of_work import UnitOfWork
from src.application.dto.book_dto import BorrowBookInputDto, BorrowBookOutputDto

class BorrowBook:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def execute(self, input_dto: BorrowBookInputDto) -> BorrowBookOutputDto:
        async with self.uow:
            book = await self.uow.books.get_by_id(input_dto.book_id)
            if not book:
                raise BookNotFoundException(f"Book with ID {input_dto.book_id} not found")
            
            book.borrow()
            
            await self.uow.books.update(book)
            await self.uow.commit()
            
            return BorrowBookOutputDto(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed
            )

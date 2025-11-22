from src.domain.entities.book import Book
from src.domain.interfaces.book_repository import BookRepository
from src.domain.interfaces.unit_of_work import UnitOfWork
from src.application.dto.book_dto import BorrowBookInputDto, BorrowBookOutputDto
from src.domain.value_objects.book_value_objects import BookId
from src.domain.interfaces.logger import Logger

class BorrowBook:
    def __init__(self, uow: UnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def execute(self, input_dto: BorrowBookInputDto) -> BorrowBookOutputDto:
        async with self.uow:
            book = await self.uow.books.get_by_id(input_dto.book_id)
            if not book:
                self.logger.warning(f"Attempted to borrow non-existent book: {input_dto.book_id}")
                raise ValueError("Book not found")
            
            book.borrow()
            
            await self.uow.books.update(book)
            await self.uow.commit()
            
            self.logger.info(f"Book borrowed successfully: {book.title.value} ({book.id.value})")
            
            return BorrowBookOutputDto(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed,
                return_due_date=book.return_due_date
            )

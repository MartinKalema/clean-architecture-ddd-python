from dataclasses import dataclass
from src.domain.catalog import UnitOfWork, BookNotFoundException, DomainException
from src.application.dto.book_dto import BookOutputDto
from src.domain.shared_kernel import Logger

@dataclass
class ReturnBookInputDto:
    book_id: str

class ReturnBook:
    def __init__(self, uow: UnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def execute(self, input_dto: ReturnBookInputDto) -> BookOutputDto:
        async with self.uow:
            book = await self.uow.books.get_by_id(input_dto.book_id)
            if not book:
                self.logger.warning(f"Attempted to return non-existent book: {input_dto.book_id}")
                raise BookNotFoundException(f"Book with id {input_dto.book_id} not found")

            book.return_book()
            await self.uow.commit()
            
            self.logger.info(f"Book returned successfully: {book.title} ({book.id})")

            return BookOutputDto(
                id=str(book.id.value),
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed
            )

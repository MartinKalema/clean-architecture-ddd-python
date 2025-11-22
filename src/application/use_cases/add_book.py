from src.domain.interfaces.unit_of_work import UnitOfWork
from src.application.dto.book_dto import AddBookInputDto, AddBookOutputDto
from src.domain.entities.book import Book
from src.domain.value_objects.book_value_objects import BookId, Title, Author
from src.domain.interfaces.logger import Logger

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

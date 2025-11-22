from src.domain.entities.book import Book
from src.domain.value_objects.book_value_objects import Title, Author
from src.domain.interfaces.unit_of_work import UnitOfWork
from src.application.dto.book_dto import AddBookInputDto, AddBookOutputDto

class AddBook:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow

    async def execute(self, input_dto: AddBookInputDto) -> AddBookOutputDto:
        # 1. Create Value Objects
        title = Title(input_dto.title)
        author = Author(input_dto.author)

        # 2. Create Entity
        book = Book(title=title, author=author)

        # 3. Persist with UoW
        async with self.uow:
            saved_book = await self.uow.books.add(book)
            await self.uow.commit()

            # 4. Return DTO
            return AddBookOutputDto(
                id=saved_book.id.value,
                title=saved_book.title.value,
                author=saved_book.author.value,
                is_borrowed=saved_book.is_borrowed
            )

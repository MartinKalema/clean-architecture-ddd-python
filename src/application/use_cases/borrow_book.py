from src.domain.catalog import UnitOfWork, BookNotFoundException
from src.domain.shared_kernel import Logger
from src.application.dto.book_dto import BorrowBookInputDto, BorrowBookOutputDto


class BorrowBook:
    def __init__(self, uow: UnitOfWork, logger: Logger):
        self.uow = uow
        self.logger = logger

    async def execute(self, input_dto: BorrowBookInputDto) -> BorrowBookOutputDto:
        async with self.uow:
            book = await self.uow.books.get_by_id(input_dto.book_id)
            if not book:
                self.logger.warning(f"Attempted to borrow non-existent book: {input_dto.book_id}")
                raise BookNotFoundException(input_dto.book_id)

            book.borrow(input_dto.borrower_email)

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

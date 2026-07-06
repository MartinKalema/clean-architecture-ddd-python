"""
Borrow Book Command - CQRS Command Side.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.domain.catalog import BookNotFoundException, BorrowerNotEligibleException

if TYPE_CHECKING:
    from src.domain.catalog import ICatalogUnitOfWork
    from src.application.query_handlers.interfaces import IPatronQueryRepository
    from src.domain.shared_kernel import ILogger


@dataclass(frozen=True)
class BorrowBookCommand:
    """Command to borrow a book."""
    book_id: str
    borrower_email: str


@dataclass(frozen=True)
class BorrowBookResult:
    """Result of borrowing a book."""
    id: str
    title: str
    author: str
    is_borrowed: bool
    status: str = "reserved"
    return_due_date: Optional[datetime] = None


class BorrowBookHandler:
    """
    Handles the BorrowBookCommand.

    Reserves the book (semantic lock) and emits CatalogBookReserved; the
    Lending context reacts by creating the loan, after which the
    reservation is confirmed into a borrow — or released on failure.
    """

    def __init__(
        self,
        uow: ICatalogUnitOfWork,
        patron_query_repository: IPatronQueryRepository,
        logger: ILogger,
    ):
        self.uow = uow
        self.patron_query_repository = patron_query_repository
        self.logger = logger

    async def handle(self, command: BorrowBookCommand) -> BorrowBookResult:
        """Execute the command to borrow a book."""
        # Pre-flight check against the patron read model: a cheap guess
        # that rejects doomed borrows BEFORE taking the reservation lock,
        # so compensation stays the exception. The read model may lag, so
        # the lending-side event handler remains the authority.
        patron = await self.patron_query_repository.find_by_email(command.borrower_email)
        if patron is None:
            raise BorrowerNotEligibleException(
                command.borrower_email, "no patron registered with this email"
            )
        if patron.is_suspended:
            raise BorrowerNotEligibleException(
                command.borrower_email, "patron is suspended"
            )

        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                self.logger.warning(f"Attempted to borrow non-existent book: {command.book_id}")
                raise BookNotFoundException(command.book_id)

            book.reserve(command.borrower_email, datetime.now())

            await self.uow.books.update(book)
            await self.uow.commit()

            self.logger.info(f"Book reserved: {book.title.value} ({book.id.value})")

            return BorrowBookResult(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed,
                status=book.status.value,
                return_due_date=book.return_due_date
            )

"""
Release Book Reservation Command - CQRS Command Side.

Compensation step of the borrow saga: the loan could not be created, so
the reservation is released and the book becomes available again.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.catalog import BookNotFoundException, BookStatus

if TYPE_CHECKING:
    from src.domain.catalog import UnitOfWork
    from src.domain.shared_kernel import ILogger


@dataclass(frozen=True)
class ReleaseBookReservationCommand:
    """Command to release a book reservation without a borrow."""
    book_id: str
    reason: str


class ReleaseBookReservationHandler:
    """Handles the ReleaseBookReservationCommand."""

    def __init__(self, uow: UnitOfWork, logger: ILogger):
        self.uow = uow
        self.logger = logger

    async def handle(self, command: ReleaseBookReservationCommand) -> None:
        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                raise BookNotFoundException(command.book_id)

            if book.status == BookStatus.AVAILABLE:
                # At-least-once redelivery: already released
                self.logger.info(
                    f"Book reservation already released: {command.book_id}"
                )
                return

            book.release(command.reason)

            await self.uow.books.update(book)
            await self.uow.commit()

            self.logger.info(
                f"Reservation released: {book.title.value} ({book.id.value}) "
                f"— {command.reason}"
            )

"""
Release Book Reservation Command - CQRS Command Side.

Compensation step of the borrow saga: the loan could not be created, so
the reservation is released and the book becomes available again.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.ports import BorrowOperationStatus
from src.domain.catalog import BookNotFoundException

if TYPE_CHECKING:
    from src.application.ports import ICatalogApplicationUnitOfWork, IClock, ILogger


@dataclass(frozen=True)
class ReleaseBookReservationCommand:
    """Command to release a book reservation without a borrow."""
    book_id: str
    reservation_id: str
    reservation_generation: int
    patron_id: str
    reason: str


class ReleaseBookReservationHandler:
    """Handles the ReleaseBookReservationCommand."""

    def __init__(self, uow: ICatalogApplicationUnitOfWork, logger: ILogger, clock: IClock):
        self.uow = uow
        self.logger = logger
        self.clock = clock

    async def handle(self, command: ReleaseBookReservationCommand) -> bool:
        async with self.uow:
            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                raise BookNotFoundException(command.book_id)

            reason = " ".join(str(command.reason).split())
            changed = book.release(
                reservation_id=command.reservation_id,
                reservation_generation=command.reservation_generation,
                patron_id=command.patron_id,
                reason=reason,
            )

            if not changed:
                self.logger.info(
                    f"Reservation already released: {command.reservation_id}"
                )
                return False

            await self.uow.books.update(book)
            await self.uow.borrow_operations.transition(
                command.reservation_id,
                BorrowOperationStatus.RELEASED,
                book_id=command.book_id,
                patron_id=command.patron_id,
                reservation_generation=command.reservation_generation,
                failure_reason=reason,
                updated_at=self.clock.now(),
            )
            await self.uow.commit()

            self.logger.info(
                f"Reservation released: {book.title.value} ({book.id.value}) "
                f"— {reason}"
            )
            return True

"""
Borrow Book Command - CQRS Command Side.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.application.ports import (
    BorrowOperation,
    BorrowOperationStatus,
    CommandReceipt,
    IdempotencyKey,
    command_fingerprint,
    require_matching_receipt,
)
from src.domain.catalog import BookNotFoundException, BorrowerNotEligibleException
from src.domain.shared_kernel import EmailAddress

if TYPE_CHECKING:
    from src.application.ports import (
        IBorrowerDirectory,
        ICatalogApplicationUnitOfWork,
        IClock,
        ILogger,
    )


@dataclass(frozen=True)
class BorrowBookCommand:
    """Command to borrow a book."""
    book_id: str
    borrower_email: str
    idempotency_key: str | None = None


@dataclass(frozen=True)
class BorrowBookResult:
    """Result of borrowing a book."""
    id: str
    title: str
    author: str
    is_borrowed: bool
    reservation_id: str
    reservation_generation: int
    operation_id: str
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
        uow: ICatalogApplicationUnitOfWork,
        borrower_directory: IBorrowerDirectory,
        logger: ILogger,
        clock: IClock,
    ):
        self.uow = uow
        self.borrower_directory = borrower_directory
        self.logger = logger
        self.clock = clock

    async def handle(self, command: BorrowBookCommand) -> BorrowBookResult:
        """Execute the command to borrow a book."""
        key = IdempotencyKey(command.idempotency_key) if command.idempotency_key else None
        email = EmailAddress(command.borrower_email).value
        request_hash = command_fingerprint(
            {"book_id": command.book_id.strip(), "borrower_email": email}
        )
        async with self.uow:
            if key:
                receipt = await self.uow.command_receipts.get(
                    "catalog.borrow_book", key.value
                )
                if receipt:
                    return BorrowBookResult(
                        **require_matching_receipt(receipt, request_hash)
                    )

            borrower = await self.borrower_directory.find_by_email(email)
            if borrower is None:
                raise BorrowerNotEligibleException(
                    email, "no patron registered with this email"
                )
            if not borrower.is_eligible:
                raise BorrowerNotEligibleException(
                    email,
                    borrower.ineligible_reason or "patron is not eligible",
                )

            book = await self.uow.books.get_by_id(command.book_id)
            if not book:
                self.logger.warning(f"Attempted to borrow non-existent book: {command.book_id}")
                raise BookNotFoundException(command.book_id)

            now = self.clock.now()
            reservation = book.reserve(
                patron_id=borrower.patron_id,
                borrower_email=borrower.email,
                reserved_at=now,
            )

            await self.uow.books.update(book)
            await self.uow.borrow_operations.add(
                BorrowOperation(
                    operation_id=reservation.value,
                    book_id=book.id.value,
                    patron_id=borrower.patron_id,
                    reservation_generation=book.reservation_generation,
                    status=BorrowOperationStatus.RESERVED,
                    created_at=now,
                    updated_at=now,
                )
            )
            result = BorrowBookResult(
                id=book.id.value,
                title=book.title.value,
                author=book.author.value,
                is_borrowed=book.is_borrowed,
                status=book.status.value,
                return_due_date=book.return_due_date,
                reservation_id=reservation.value,
                reservation_generation=book.reservation_generation,
                operation_id=reservation.value,
            )
            if key:
                await self.uow.command_receipts.add(
                    CommandReceipt(
                        scope="catalog.borrow_book",
                        idempotency_key=key.value,
                        request_hash=request_hash,
                        response=result.__dict__,
                    )
                )
            await self.uow.commit()

            self.logger.info(f"Book reserved: {book.title.value} ({book.id.value})")

            return result

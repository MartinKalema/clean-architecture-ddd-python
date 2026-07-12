"""Query the durable state of an accepted asynchronous borrow workflow."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.application.exceptions import BorrowOperationNotFoundException

if TYPE_CHECKING:
    from src.application.ports import ICatalogApplicationUnitOfWork


@dataclass(frozen=True)
class GetBorrowOperationQuery:
    operation_id: str


@dataclass(frozen=True)
class BorrowOperationResult:
    operation_id: str
    book_id: str
    patron_id: str
    reservation_generation: int
    status: str
    loan_id: str | None
    failure_reason: str | None
    created_at: datetime | None
    updated_at: datetime | None


class GetBorrowOperationHandler:
    """Keep workflow-status reads separate from the mutating borrow command."""

    def __init__(self, uow: "ICatalogApplicationUnitOfWork") -> None:
        self._uow = uow

    async def handle(self, query: GetBorrowOperationQuery) -> BorrowOperationResult:
        async with self._uow:
            operation = await self._uow.borrow_operations.get(query.operation_id)
            if operation is None:
                raise BorrowOperationNotFoundException(query.operation_id)
            return BorrowOperationResult(
                operation_id=operation.operation_id,
                book_id=operation.book_id,
                patron_id=operation.patron_id,
                reservation_generation=operation.reservation_generation,
                status=operation.status.value,
                loan_id=operation.loan_id,
                failure_reason=operation.failure_reason,
                created_at=operation.created_at,
                updated_at=operation.updated_at,
            )

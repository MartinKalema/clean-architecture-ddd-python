"""Durable process state for the asynchronous borrow workflow."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class BorrowOperationStatus(str, Enum):
    RESERVED = "reserved"
    BORROWED = "borrowed"
    RELEASED = "released"
    RETURNED = "returned"


@dataclass(frozen=True)
class BorrowOperation:
    operation_id: str
    book_id: str
    patron_id: str
    reservation_generation: int
    status: BorrowOperationStatus
    created_at: datetime
    updated_at: datetime
    loan_id: str | None = None
    failure_reason: str | None = None


class IBorrowOperationRepository(Protocol):
    async def add(self, operation: BorrowOperation) -> None:
        ...

    async def get(self, operation_id: str) -> BorrowOperation | None:
        ...

    async def transition(
        self,
        operation_id: str,
        status: BorrowOperationStatus,
        *,
        book_id: str,
        patron_id: str,
        reservation_generation: int,
        loan_id: str | None = None,
        failure_reason: str | None = None,
        updated_at: datetime,
    ) -> None:
        ...

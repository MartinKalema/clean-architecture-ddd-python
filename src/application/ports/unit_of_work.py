"""Application transactions compose domain repositories and workflow state."""
from typing import Protocol

from src.application.ports.borrow_operations import IBorrowOperationRepository
from src.application.ports.idempotency import ICommandReceiptRepository
from src.domain.catalog import IBookCommandRepository
from src.domain.lending import ILoanCommandRepository
from src.domain.patron import IPatronCommandRepository


class _IUnitOfWork(Protocol):
    async def __aenter__(self): ...
    async def __aexit__(self, exc_type, exc_val, exc_tb): ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class ICatalogApplicationUnitOfWork(_IUnitOfWork, Protocol):
    books: IBookCommandRepository
    command_receipts: ICommandReceiptRepository
    borrow_operations: IBorrowOperationRepository


class ILendingApplicationUnitOfWork(_IUnitOfWork, Protocol):
    loans: ILoanCommandRepository
    command_receipts: ICommandReceiptRepository

    async def acquire_borrowing_fence(self, patron_id: str) -> None: ...


class IPatronApplicationUnitOfWork(_IUnitOfWork, Protocol):
    patrons: IPatronCommandRepository
    command_receipts: ICommandReceiptRepository

    async def acquire_borrowing_fence(self, patron_id: str) -> None: ...

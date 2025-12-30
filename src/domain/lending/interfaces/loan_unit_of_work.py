"""
Unit of Work interface for the Lending bounded context.
"""
from typing import Protocol

from src.domain.lending.interfaces.loan_command_repository import ILoanCommandRepository


class ILoanUnitOfWork(Protocol):
    """Unit of Work interface for managing Loan transactions."""
    loans: ILoanCommandRepository

    async def __aenter__(self) -> "ILoanUnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    async def commit(self):
        ...

    async def rollback(self):
        ...

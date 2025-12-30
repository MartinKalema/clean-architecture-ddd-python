"""
Unit of Work interface for the Patron bounded context.
"""
from typing import Protocol

from src.domain.patron.interfaces.patron_command_repository import IPatronCommandRepository


class IPatronUnitOfWork(Protocol):
    """Unit of Work interface for managing Patron transactions."""
    patrons: IPatronCommandRepository

    async def __aenter__(self) -> "IPatronUnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    async def commit(self):
        ...

    async def rollback(self):
        ...

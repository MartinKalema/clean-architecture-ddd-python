"""
Unit of Work interface for the Catalog bounded context.
"""
from typing import Protocol

from src.domain.catalog.interfaces.catalog_command_repository import IBookCommandRepository


class ICatalogUnitOfWork(Protocol):
    """Unit of Work interface for managing Catalog transactions."""
    books: IBookCommandRepository

    async def __aenter__(self) -> "ICatalogUnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    async def commit(self):
        ...

    async def rollback(self):
        ...

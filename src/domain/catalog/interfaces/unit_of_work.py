"""
Unit of Work interface for the Catalog bounded context.
"""
from typing import Protocol

from src.domain.catalog.interfaces.catalog_book_repository import BookRepository


class UnitOfWork(Protocol):
    """Unit of Work for managing transactions."""
    books: BookRepository

    async def __aenter__(self) -> "UnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    async def commit(self):
        ...

    async def rollback(self):
        ...

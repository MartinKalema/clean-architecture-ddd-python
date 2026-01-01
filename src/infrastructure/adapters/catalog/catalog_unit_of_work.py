"""
Catalog Unit of Work - Infrastructure implementation.

Implements: ICatalogUnitOfWork
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from src.infrastructure.adapters.catalog.book_command_repository import (
    BookCommandRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from src.domain.catalog import Book
    from src.domain.shared_kernel import ILogger


class CatalogUnitOfWork:
    """
    Unit of Work pattern implementation for Catalog bounded context.

    Manages transactions and tracks aggregates within a session.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: Optional[ILogger] = None
    ):
        self.session_factory = session_factory
        self.logger = logger
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "CatalogUnitOfWork":
        self._session = self.session_factory()
        self.identity_map: Dict[str, Book] = {}
        self.books = BookCommandRepository(self._session, self.identity_map)
        return self

    async def __aexit__(self, exc_type, _exc_val, _exc_tb):
        if exc_type:
            await self.rollback()
        await self._session.close()
        self._session = None

    async def commit(self):
        if self._session:
            await self._session.commit()

    async def rollback(self):
        if self._session:
            await self._session.rollback()

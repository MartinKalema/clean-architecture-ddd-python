"""
Book Query Repository - CQRS Read Side Implementation.

Implements: IBookQueryRepository
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.query_handlers import BookReadModel
from src.infrastructure.adapters.catalog.book_model import BookModel


class BookQueryRepository:
    """
    Book Query Repository implementation.

    Optimized for read operations with:
    - Direct SQL queries (no ORM overhead for writes)
    - Optional caching layer
    - Pagination support
    - Flexible filtering
    """

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def find_by_id(self, book_id: str) -> Optional[BookReadModel]:
        """Find a book by its ID."""
        async with self._session_factory() as session:
            stmt = select(BookModel).where(BookModel.id == book_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if not row:
                return None

            return self._to_read_model(row)

    async def find_all(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
        author_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BookReadModel]:
        """Find books with optional filters."""
        async with self._session_factory() as session:
            stmt = select(BookModel)

            if only_available:
                stmt = stmt.where(BookModel.is_borrowed.is_(False))
            if only_borrowed:
                stmt = stmt.where(BookModel.is_borrowed.is_(True))
            if author_contains:
                stmt = stmt.where(BookModel.author.ilike(f"%{author_contains}%"))
            if title_contains:
                stmt = stmt.where(BookModel.title.ilike(f"%{title_contains}%"))

            stmt = stmt.offset(offset).limit(limit)

            stmt = stmt.order_by(BookModel.title)

            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [self._to_read_model(row) for row in rows]

    async def count(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
    ) -> int:
        """Count books matching criteria."""
        async with self._session_factory() as session:
            stmt = select(func.count(BookModel.id))

            if only_available:
                stmt = stmt.where(BookModel.is_borrowed.is_(False))
            if only_borrowed:
                stmt = stmt.where(BookModel.is_borrowed.is_(True))

            result = await session.execute(stmt)
            return result.scalar_one()

    def _to_read_model(self, row: BookModel) -> BookReadModel:
        """Convert database row to read model."""
        return BookReadModel(
            id=row.id,
            title=row.title,
            author=row.author,
            is_borrowed=row.is_borrowed,
            borrowed_at=row.borrowed_at,
            return_due_date=row.return_due_date,
        )

"""
SQL Book Query Repository - CQRS Read Side Implementation.

This repository is optimized for read operations. In a full CQRS setup,
this could read from:
- A separate read-optimized database
- Denormalized views
- A cache layer (Redis)
- A search engine (Elasticsearch)

For now, it reads from the same database but with read-optimized queries.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.application.queries import BookReadModel
from src.infrastructure.adapters.repositories.sql_book_repository import BookModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class SQLBookQueryRepository:
    """
    SQL implementation of the Book Query Repository.

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

            # Apply filters
            if only_available:
                stmt = stmt.where(BookModel.is_borrowed == False)
            if only_borrowed:
                stmt = stmt.where(BookModel.is_borrowed == True)
            if author_contains:
                stmt = stmt.where(BookModel.author.ilike(f"%{author_contains}%"))
            if title_contains:
                stmt = stmt.where(BookModel.title.ilike(f"%{title_contains}%"))

            # Apply pagination
            stmt = stmt.offset(offset).limit(limit)

            # Order by title for consistent results
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
                stmt = stmt.where(BookModel.is_borrowed == False)
            if only_borrowed:
                stmt = stmt.where(BookModel.is_borrowed == True)

            result = await session.execute(stmt)
            return result.scalar_one()

    def _to_read_model(self, row: BookModel) -> BookReadModel:
        """Convert database row to read model."""
        return BookReadModel(
            id=row.id,
            title=row.title,
            author=row.author,
            is_borrowed=row.is_borrowed,
            borrower_email=row.borrower_email,
            borrowed_at=row.borrowed_at,
            return_due_date=row.return_due_date,
        )

from typing import Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, String, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.catalog import (
    Author,
    Book,
    BookId,
    ConcurrentModificationException,
    Title,
)
from src.infrastructure.exceptions import DatabaseException
from src.infrastructure.external.database import Base


class BookModel(Base):
    """SQLAlchemy model for Book aggregate."""
    __tablename__ = "books"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, index=True)
    author = Column(String)
    is_borrowed = Column(Boolean, default=False)
    borrowed_at = Column(DateTime, nullable=True)
    return_due_date = Column(DateTime, nullable=True)
    version = Column(Integer, default=0, nullable=False)

    def to_entity(self) -> Book:
        """Convert DB model to domain entity."""
        book = Book(
            id=BookId(self.id),
            title=Title(self.title),
            author=Author(self.author),
            is_borrowed=self.is_borrowed,
            borrowed_at=self.borrowed_at,
            return_due_date=self.return_due_date
        )
        # Set the internal version from DB
        book._version = self.version
        return book

    @staticmethod
    def from_entity(book: Book) -> "BookModel":
        """Convert domain entity to DB model."""
        return BookModel(
            id=book.id.value,
            title=book.title.value,
            author=book.author.value,
            is_borrowed=book.is_borrowed,
            borrowed_at=book.borrowed_at,
            return_due_date=book.return_due_date,
            version=book.version
        )


class SQLBookRepository:
    """Repository implementation with optimistic locking support."""

    def __init__(self, session: AsyncSession, identity_map: Optional[Dict[str, Book]] = None):
        self.session = session
        self.identity_map = identity_map if identity_map is not None else {}

    async def add(self, book: Book) -> Book:
        try:
            db_book = BookModel.from_entity(book)
            self.session.add(db_book)

            # Track entity for events using entity ID as key
            self.identity_map[book.id.value] = book

            # Return the same entity instance to preserve identity
            return book
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error adding book: {str(e)}", original_exception=e)

    async def get_all(self) -> List[Book]:
        try:
            result = await self.session.execute(select(BookModel))
            db_books = result.scalars().all()
            entities = []
            for db_book in db_books:
                # Check identity map first to return tracked instance
                if db_book.id in self.identity_map:
                    entities.append(self.identity_map[db_book.id])
                else:
                    entity = db_book.to_entity()
                    self.identity_map[entity.id.value] = entity
                    entities.append(entity)
            return entities
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving books: {str(e)}", original_exception=e)

    async def get_by_id(self, book_id: str) -> Optional[Book]:
        try:
            # Check identity map first to return tracked instance
            if book_id in self.identity_map:
                return self.identity_map[book_id]

            result = await self.session.execute(select(BookModel).filter(BookModel.id == book_id))
            db_book = result.scalars().first()
            if db_book:
                entity = db_book.to_entity()
                # Track entity in identity map for event collection
                self.identity_map[entity.id.value] = entity
                return entity
            return None
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving book {book_id}: {str(e)}", original_exception=e)

    async def update(self, book: Book) -> None:
        """
        Update a book with optimistic locking.

        Uses WHERE version = expected_version to ensure no concurrent modification.
        If the update affects 0 rows, it means the version changed (concurrent modification).
        """
        try:
            expected_version = book.version
            new_version = expected_version + 1

            # Update only if version matches (optimistic locking)
            result = await self.session.execute(
                update(BookModel)
                .where(BookModel.id == book.id.value)
                .where(BookModel.version == expected_version)
                .values(
                    is_borrowed=book.is_borrowed,
                    borrowed_at=book.borrowed_at,
                    return_due_date=book.return_due_date,
                    version=new_version
                )
            )

            if result.rowcount == 0:
                # Either the book doesn't exist or version mismatch
                # Check if book exists
                check_result = await self.session.execute(
                    select(BookModel).filter(BookModel.id == book.id.value)
                )
                if check_result.scalars().first() is None:
                    raise DatabaseException(f"Book {book.id.value} not found")
                else:
                    raise ConcurrentModificationException("Book", book.id.value)

            # Update the entity's version
            book._version = new_version

            # Track entity for events (may already be tracked from get_by_id)
            self.identity_map[book.id.value] = book

        except ConcurrentModificationException:
            raise
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error updating book {book.id.value}: {str(e)}", original_exception=e)

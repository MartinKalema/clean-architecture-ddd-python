from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.domain.entities.book import Book
from src.domain.value_objects.book_value_objects import BookId, Title, Author
from src.infrastructure.external.database import Base

from sqlalchemy.exc import SQLAlchemyError
from src.infrastructure.exceptions import DatabaseException


class BookModel(Base):
    __tablename__ = "books"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, index=True)
    author = Column(String)
    is_borrowed = Column(Boolean, default=False)
    borrowed_at = Column(DateTime, nullable=True)
    return_due_date = Column(DateTime, nullable=True)

    def to_entity(self) -> Book:
        return Book(
            id=BookId(self.id),
            title=Title(self.title),
            author=Author(self.author),
            is_borrowed=self.is_borrowed,
            borrowed_at=self.borrowed_at,
            return_due_date=self.return_due_date
        )

    @staticmethod
    def from_entity(book: Book) -> "BookModel":
        return BookModel(
            id=book.id.value,
            title=book.title.value,
            author=book.author.value,
            is_borrowed=book.is_borrowed,
            borrowed_at=book.borrowed_at,
            return_due_date=book.return_due_date
        )


class SQLBookRepository:
    def __init__(self, session: AsyncSession, identity_map: Dict[str, Book] = None):
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
        try:
            result = await self.session.execute(select(BookModel).filter(BookModel.id == book.id.value))
            db_book = result.scalars().first()
            if db_book:
                db_book.is_borrowed = book.is_borrowed
                db_book.borrowed_at = book.borrowed_at
                db_book.return_due_date = book.return_due_date

                # Track entity for events (may already be tracked from get_by_id)
                self.identity_map[book.id.value] = book
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error updating book {book.id.value}: {str(e)}", original_exception=e)

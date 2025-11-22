from typing import List, Optional
from sqlalchemy import Column, String, Boolean, select
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

    def to_entity(self) -> Book:
        return Book(
            id=BookId(self.id),
            title=Title(self.title),
            author=Author(self.author),
            is_borrowed=self.is_borrowed
        )

    @staticmethod
    def from_entity(book: Book) -> "BookModel":
        return BookModel(
            id=book.id.value,
            title=book.title.value,
            author=book.author.value,
            is_borrowed=book.is_borrowed
        )

class SQLBookRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, book: Book) -> Book:
        try:
            db_book = BookModel.from_entity(book)
            self.session.add(db_book)
            # We don't commit here. UoW handles it.
            # We might flush if we needed DB-generated IDs, but we use UUIDs.
            return db_book.to_entity()
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error adding book: {str(e)}", original_exception=e)

    async def get_all(self) -> List[Book]:
        try:
            result = await self.session.execute(select(BookModel))
            db_books = result.scalars().all()
            return [db_book.to_entity() for db_book in db_books]
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving books: {str(e)}", original_exception=e)

    async def get_by_id(self, book_id: str) -> Optional[Book]:
        try:
            result = await self.session.execute(select(BookModel).filter(BookModel.id == book_id))
            db_book = result.scalars().first()
            if db_book:
                return db_book.to_entity()
            return None
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving book {book_id}: {str(e)}", original_exception=e)

    async def update(self, book: Book) -> None:
        try:
            result = await self.session.execute(select(BookModel).filter(BookModel.id == book.id.value))
            db_book = result.scalars().first()
            if db_book:
                db_book.is_borrowed = book.is_borrowed
                # No commit here.
                
                # Dispatch Domain Events (Placeholder - will move to UoW/Dispatcher later)
                for event in book.get_domain_events():
                    print(f"[EVENT DISPATCHED]: {event}")
                book.clear_events()
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error updating book {book.id.value}: {str(e)}", original_exception=e)

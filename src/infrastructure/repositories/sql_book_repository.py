from typing import List, Optional
from sqlalchemy import Column, String, Boolean, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.domain.entities.book import Book
from src.domain.value_objects.book_value_objects import BookId, Title, Author
from src.domain.interfaces.book_repository import BookRepository
from src.infrastructure.external.database import Base

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

class SQLBookRepository(BookRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, book: Book) -> Book:
        db_book = BookModel.from_entity(book)
        self.session.add(db_book)
        await self.session.commit()
        await self.session.refresh(db_book)
        return db_book.to_entity()

    async def get_all(self) -> List[Book]:
        result = await self.session.execute(select(BookModel))
        db_books = result.scalars().all()
        return [db_book.to_entity() for db_book in db_books]

    async def get_by_id(self, book_id: str) -> Optional[Book]:
        result = await self.session.execute(select(BookModel).filter(BookModel.id == book_id))
        db_book = result.scalars().first()
        if db_book:
            return db_book.to_entity()
        return None

    async def update(self, book: Book) -> None:
        result = await self.session.execute(select(BookModel).filter(BookModel.id == book.id.value))
        db_book = result.scalars().first()
        if db_book:
            db_book.is_borrowed = book.is_borrowed
            await self.session.commit()
            
            # Dispatch Domain Events
            for event in book.get_domain_events():
                print(f"[EVENT DISPATCHED]: {event}")
            book.clear_events()

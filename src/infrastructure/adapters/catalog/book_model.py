"""
SQLAlchemy models for Catalog bounded context.

These models are shared between command and query repositories.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from src.domain.catalog import Author, Book, BookId, Title
from src.infrastructure.external.postgresql import Base


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
            return_due_date=self.return_due_date,
        )
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
            version=book.version,
        )

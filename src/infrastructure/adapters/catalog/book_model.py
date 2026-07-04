"""
SQLAlchemy models for Catalog bounded context.

These models are shared between command and query repositories.
"""
from sqlalchemy import Column, DateTime, Integer, String

from src.domain.catalog import Author, Book, BookId, BookStatus, Title
from src.infrastructure.external.postgresql import Base


class BookModel(Base):
    """SQLAlchemy model for Book aggregate."""

    __tablename__ = "books"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, index=True)
    author = Column(String)
    status = Column(String, default=BookStatus.AVAILABLE.value, nullable=False, index=True)
    reserved_at = Column(DateTime, nullable=True)
    borrowed_at = Column(DateTime, nullable=True)
    return_due_date = Column(DateTime, nullable=True)
    version = Column(Integer, default=0, nullable=False)

    def to_entity(self) -> Book:
        """Convert DB model to domain entity."""
        book = Book(
            id=BookId(self.id),
            title=Title(self.title),
            author=Author(self.author),
            status=BookStatus(self.status),
            reserved_at=self.reserved_at,
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
            status=book.status.value,
            reserved_at=book.reserved_at,
            borrowed_at=book.borrowed_at,
            return_due_date=book.return_due_date,
            version=book.version,
        )

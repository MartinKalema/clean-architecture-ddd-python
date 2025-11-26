"""
Catalog Bounded Context

Manages the library's book catalog including borrowing behavior.
"""
from .entities import Book
from .value_objects import BookId, Title, Author, ISBN
from .events import BookAddedToCatalog, BookRemovedFromCatalog, BookBorrowed, BookReturned
from .interfaces import BookRepository, UnitOfWork
from .exceptions import (
    DomainException,
    ValidationException,
    BookNotFoundException,
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
)

__all__ = [
    # Entities
    "Book",
    # Value Objects
    "BookId",
    "Title",
    "Author",
    "ISBN",
    # Events
    "BookAddedToCatalog",
    "BookRemovedFromCatalog",
    "BookBorrowed",
    "BookReturned",
    # Interfaces
    "BookRepository",
    "UnitOfWork",
    # Exceptions
    "DomainException",
    "ValidationException",
    "BookNotFoundException",
    "BookAlreadyBorrowedException",
    "BookNotBorrowedException",
]

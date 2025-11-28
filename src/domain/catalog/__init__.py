"""
Catalog Bounded Context

Manages the library's book catalog including borrowing behavior.
"""
from .entities import Book
from .value_objects import BookId, Title, Author, ISBN
from .events import BookAddedToCatalog, BookRemovedFromCatalog, BookBorrowed, BookReturned
from .interfaces import BookRepository, BookQueryRepository, UnitOfWork
from src.domain.shared_kernel.exceptions import DomainException, ValidationException
from .exceptions import (
    CatalogException,
    BookNotFoundException,
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
    BorrowerEmailRequiredException,
    ConcurrentModificationException,
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
    "BookQueryRepository",
    "UnitOfWork",
    # Exceptions
    "DomainException",
    "ValidationException",
    "CatalogException",
    "BookNotFoundException",
    "BookAlreadyBorrowedException",
    "BookNotBorrowedException",
    "BorrowerEmailRequiredException",
    "ConcurrentModificationException",
]

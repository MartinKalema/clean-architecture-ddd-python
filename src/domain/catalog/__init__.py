"""
Catalog Bounded Context

Manages the library's book catalog including borrowing behavior.
"""
from src.domain.shared_kernel.exceptions import DomainException, ValidationException

from .entities import Book
from .events import (
    BookAddedToCatalog,
    BookRemovedFromCatalog,
    CatalogBookBorrowed,
    CatalogBookReturned,
)
from .exceptions import (
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
    BookNotFoundException,
    BorrowerEmailRequiredException,
    CatalogException,
    ConcurrentModificationException,
)
from .interfaces import BookQueryRepository, BookRepository, UnitOfWork
from .value_objects import ISBN, Author, BookId, Title

__all__ = [
    "Book",
    "BookId",
    "Title",
    "Author",
    "ISBN",
    "BookAddedToCatalog",
    "BookRemovedFromCatalog",
    "CatalogBookBorrowed",
    "CatalogBookReturned",
    "BookRepository",
    "BookQueryRepository",
    "UnitOfWork",
    "DomainException",
    "ValidationException",
    "CatalogException",
    "BookNotFoundException",
    "BookAlreadyBorrowedException",
    "BookNotBorrowedException",
    "BorrowerEmailRequiredException",
    "ConcurrentModificationException",
]

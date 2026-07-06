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
    CatalogBookReleased,
    CatalogBookReserved,
    CatalogBookReturned,
)
from .exceptions import (
    BookAlreadyBorrowedException,
    BookNotBorrowedException,
    BookNotFoundException,
    BookNotReservedException,
    BorrowerEmailRequiredException,
    BorrowerNotEligibleException,
    CatalogException,
    ConcurrentModificationException,
)
from .interfaces import IBookCommandRepository, ICatalogUnitOfWork
from .value_objects import ISBN, Author, BookId, BookStatus, Title

__all__ = [
    "Book",
    "BookId",
    "BookStatus",
    "Title",
    "Author",
    "ISBN",
    "BookAddedToCatalog",
    "BookRemovedFromCatalog",
    "CatalogBookBorrowed",
    "CatalogBookReleased",
    "CatalogBookReserved",
    "CatalogBookReturned",
    "IBookCommandRepository",
    "ICatalogUnitOfWork",
    "DomainException",
    "ValidationException",
    "CatalogException",
    "BookNotFoundException",
    "BookAlreadyBorrowedException",
    "BookNotBorrowedException",
    "BookNotReservedException",
    "BorrowerEmailRequiredException",
    "BorrowerNotEligibleException",
    "ConcurrentModificationException",
]

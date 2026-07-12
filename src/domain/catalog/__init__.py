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
    InvalidBorrowPeriodException,
    InvalidCatalogReferenceException,
    InvalidCatalogStateException,
    InvalidReservationReasonException,
    LoanCorrelationMismatchException,
    StaleLoanCompletionException,
    StaleReservationException,
)
from .interfaces import IBookCommandRepository
from .value_objects import ISBN, Author, BookId, BookStatus, ReservationId, Title

__all__ = [
    "Book",
    "BookId",
    "ReservationId",
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
    "StaleReservationException",
    "LoanCorrelationMismatchException",
    "StaleLoanCompletionException",
    "InvalidBorrowPeriodException",
    "InvalidCatalogReferenceException",
    "InvalidCatalogStateException",
    "InvalidReservationReasonException",
]

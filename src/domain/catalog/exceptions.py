"""
Exceptions for the Catalog bounded context.
"""
from src.domain.shared_kernel.exceptions import DomainException


class CatalogException(DomainException):
    """Base class for catalog domain exceptions."""


class BookNotFoundException(CatalogException):
    """Raised when a book is not found in the catalog."""
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} not found")


class BookAlreadyBorrowedException(CatalogException):
    """Raised when attempting to borrow an already borrowed book."""
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} is already borrowed")


class BookNotBorrowedException(CatalogException):
    """Raised when attempting to return a book that is not borrowed."""
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} is not borrowed")


class BookNotReservedException(CatalogException):
    """Raised when confirming or releasing a book that is not reserved."""
    def __init__(self, book_id: str, status: str):
        super().__init__(
            f"Book with id {book_id} is not reserved (status: {status})"
        )


class BorrowerNotEligibleException(CatalogException):
    """Raised when the borrower cannot borrow (unknown or suspended)."""
    def __init__(self, borrower_email: str, reason: str):
        super().__init__(
            f"Borrower {borrower_email} cannot borrow: {reason}"
        )


class BorrowerEmailRequiredException(CatalogException):
    """Raised when borrower email is not provided."""
    def __init__(self):
        super().__init__("Borrower email is required")


class ConcurrentModificationException(CatalogException):
    """
    Raised when optimistic locking fails due to concurrent modification.

    This indicates that another process modified the aggregate since it was
    loaded. The operation should be retried with a fresh copy.
    """
    def __init__(self, aggregate_type: str, aggregate_id: str):
        super().__init__(
            f"{aggregate_type} with id {aggregate_id} was modified by another process. "
            "Please retry the operation."
        )

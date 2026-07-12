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


class StaleReservationException(CatalogException):
    """
    Raised when an asynchronous message targets a different borrow attempt.

    This is deliberately distinct from optimistic-lock conflicts: consumers
    may acknowledge a stale message, while concurrent writes and transient
    infrastructure failures remain retryable.
    """

    def __init__(
        self,
        book_id: str,
        reservation_id: str,
        reservation_generation: int,
        operation: str,
    ):
        super().__init__(
            f"Cannot {operation} book {book_id}: reservation "
            f"{reservation_id}/{reservation_generation} is stale"
        )


class LoanCorrelationMismatchException(CatalogException):
    """Raised when a return does not target the book's current loan."""

    def __init__(self, book_id: str, loan_id: str, detail: str | None = None):
        suffix = f" ({detail})" if detail else ""
        super().__init__(
            f"Cannot return book {book_id}: loan {loan_id} does not match "
            f"the current borrow{suffix}"
        )


class StaleLoanCompletionException(LoanCorrelationMismatchException):
    """Raised when an old completion targets a superseded Catalog workflow."""


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


class InvalidCatalogReferenceException(CatalogException):
    """Raised when an external identity carried into Catalog is invalid."""

    def __init__(self, field: str):
        super().__init__(f"{field} has an invalid value")


class InvalidReservationReasonException(CatalogException):
    """Raised when reservation compensation lacks a bounded reason."""

    def __init__(self):
        super().__init__("Reservation release reason must be between 1 and 500 characters")


class InvalidBorrowPeriodException(CatalogException):
    """Raised when Lending supplies impossible authoritative loan dates."""

    def __init__(self):
        super().__init__("Borrow due date must be after the borrow timestamp")


class InvalidCatalogStateException(CatalogException):
    """Raised when construction/rehydration violates the Book state machine."""

    def __init__(self, detail: str):
        super().__init__(f"Invalid catalog book state: {detail}")


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

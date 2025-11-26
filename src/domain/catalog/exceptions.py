"""
Exceptions for the Catalog bounded context.
"""


class DomainException(Exception):
    """Base class for all domain exceptions."""
    pass


class ValidationException(DomainException):
    """Raised when validation fails."""
    def __init__(self, message: str):
        super().__init__(message)


class BookNotFoundException(DomainException):
    """Raised when a book is not found in the catalog."""
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} not found.")


class BookAlreadyBorrowedException(DomainException):
    """Raised when attempting to borrow an already borrowed book."""
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} is already borrowed.")


class BookNotBorrowedException(DomainException):
    """Raised when attempting to return a book that is not borrowed."""
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} is not borrowed.")


class ConcurrentModificationException(DomainException):
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

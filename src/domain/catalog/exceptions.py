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

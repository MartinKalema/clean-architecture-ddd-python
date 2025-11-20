class DomainException(Exception):
    """Base class for all domain exceptions."""
    pass

class BookNotFoundException(DomainException):
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} not found.")

class BookAlreadyBorrowedException(DomainException):
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} is already borrowed.")

class BookNotBorrowedException(DomainException):
    def __init__(self, book_id: str):
        super().__init__(f"Book with id {book_id} is not borrowed.")

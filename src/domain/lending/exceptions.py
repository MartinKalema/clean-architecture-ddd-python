"""
Exceptions for the Lending bounded context.
"""
from src.domain.shared_kernel.exceptions import DomainException


class LendingException(DomainException):
    """Base class for lending domain exceptions."""
    pass


class LoanAlreadyReturnedException(LendingException):
    """Raised when attempting to return an already returned loan."""
    def __init__(self, loan_id: str):
        super().__init__(f"Loan {loan_id} is already returned")


class LoanNotActiveException(LendingException):
    """Raised when an operation requires an active loan."""
    def __init__(self, loan_id: str, operation: str):
        super().__init__(f"Cannot {operation}: Loan {loan_id} is not active")


class LoanNotOverdueException(LendingException):
    """Raised when attempting to mark a loan overdue that isn't past due."""
    def __init__(self, loan_id: str):
        super().__init__(f"Loan {loan_id} is not past its due date")


class CannotExtendOverdueLoanException(LendingException):
    """Raised when attempting to extend an overdue loan."""
    def __init__(self, loan_id: str):
        super().__init__(f"Cannot extend loan {loan_id}: loan is overdue")


class BookNotAvailableException(LendingException):
    """Raised when attempting to check out an unavailable book."""
    def __init__(self, book_id: str):
        super().__init__(f"Book {book_id} is not available for checkout")


class BookNotCheckedOutException(LendingException):
    """Raised when attempting to check in a book that isn't checked out."""
    def __init__(self, book_id: str):
        super().__init__(f"Book {book_id} is not checked out")


class InvalidLoanIdException(LendingException):
    """Raised when a loan ID is invalid."""
    def __init__(self):
        super().__init__("LoanId cannot be empty")

"""
Exceptions for the Lending bounded context.
"""
from src.domain.shared_kernel.exceptions import DomainException


class LendingException(DomainException):
    """Base class for lending domain exceptions."""


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


class InvalidLoanIdException(LendingException):
    """Raised when a loan ID is invalid."""
    def __init__(self):
        super().__init__("LoanId cannot be empty")


class InvalidReservationIdException(LendingException):
    """Raised when a reservation correlation token is not a UUID."""

    def __init__(self):
        super().__init__("ReservationId must be a valid UUID")


class InvalidLoanDurationException(LendingException):
    """Raised when a new loan would have no positive lending period."""

    def __init__(self, days: int):
        super().__init__(f"Loan duration must be positive (received {days} days)")


class InvalidLoanExtensionException(LendingException):
    """Raised when an extension would not move the due date forward."""

    def __init__(self, days: int):
        super().__init__(f"Loan extension must be positive (received {days} days)")


class InvalidLoanReturnDateException(LendingException):
    """Raised when a return predates the borrow."""

    def __init__(self, loan_id: str):
        super().__init__(f"Loan {loan_id} cannot be returned before it was borrowed")


class InvalidLoanReferenceException(LendingException):
    """Raised when a cross-context identity or immutable snapshot is invalid."""

    def __init__(self, field: str):
        super().__init__(f"{field} has an invalid value")


class InvalidLoanStateException(LendingException):
    """Raised when construction/rehydration violates Loan lifecycle state."""

    def __init__(self, detail: str):
        super().__init__(f"Invalid loan state: {detail}")


class InvalidCancellationReasonException(LendingException):
    """Raised when cancellation lacks a bounded reason."""

    def __init__(self):
        super().__init__("Cancellation reason must be between 1 and 500 characters")


class InvalidReservationGenerationException(LendingException):
    """Raised when a fencing generation is absent or non-positive."""

    def __init__(self, generation: int):
        super().__init__(
            "Reservation generation must be positive "
            f"(received {generation})"
        )


class ReservationCorrelationMismatchException(LendingException):
    """
    Raised when a replay reuses a reservation token with different facts.

    A reservation id is an idempotency identity, not merely a lookup hint.  A
    caller finding an existing loan must compare generation, book, and patron;
    any disagreement is a domain conflict and must not be treated as success.
    """

    def __init__(self, reservation_id: str, detail: str):
        super().__init__(
            f"Reservation {reservation_id} conflicts with its existing loan: {detail}"
        )


class ConcurrentLoanCreationException(LendingException):
    """Raised when a database uniqueness race must be reconciled by identity."""

    def __init__(self, reservation_id: str, book_id: str):
        self.reservation_id = reservation_id
        self.book_id = book_id
        super().__init__(
            f"Concurrent loan creation for reservation {reservation_id} "
            f"and book {book_id}"
        )


class ConcurrentModificationException(LendingException):
    """Raised when optimistic locking detects a concurrently changed loan."""

    def __init__(self, loan_id: str):
        super().__init__(f"Loan {loan_id} was modified by another process")


class PatronBorrowingLimitReachedException(LendingException):
    """Raised when a patron already holds the tier's outstanding-loan limit."""

    def __init__(self, patron_id: str, limit: int):
        self.patron_id = patron_id
        self.limit = limit
        super().__init__(
            f"Patron {patron_id} has reached the borrowing limit of {limit}"
        )


class PatronNotEligibleForLoanException(LendingException):
    """Authoritative Patron state rejected final Lending acceptance."""

    def __init__(self, patron_id: str, reason: str):
        self.patron_id = patron_id
        self.reason = reason
        super().__init__(f"Patron {patron_id} is not eligible for a loan: {reason}")


class LoanNotFoundException(LendingException):
    """Raised when a loan is not found."""
    def __init__(self, loan_id: str):
        super().__init__(f"Loan with id {loan_id} not found")

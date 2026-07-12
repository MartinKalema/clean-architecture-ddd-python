"""
Lending Bounded Context

This is the CORE DOMAIN - the most important bounded context in the library
system. It handles the lending of books to patrons.

Responsibilities:
- Managing book loans (borrowing and returning)
- Tracking due dates and overdue items
- Enforcing borrowing rules and limits
- Managing holds and reservations

Key Aggregate:
- Loan: Represents an active, terminal, overdue, or lost book loan

Ubiquitous Language:
- Loan: The act of lending a book to a patron
- DueDate: When the book must be returned
- Overdue: A book not returned by its due date

Context Relationships:
- Downstream from Catalog: Uses CatalogBookId to reference books
- Downstream from Patron: Uses PatronId to reference borrowers
- Uses Anti-Corruption Layer to translate from upstream contexts

Anti-Corruption Layer (ACL):
The ACL protects this context from changes in upstream contexts. If Catalog
or Patron change their models, only the ACL needs to be updated.
"""
from .entities.loan import Loan
from .events.lending_events import (
    BookOverdue,
    LoanCancelled,
    LoanCompleted,
    LoanCreated,
    LoanExtended,
)
from .exceptions import (
    BookNotAvailableException,
    CannotExtendOverdueLoanException,
    ConcurrentLoanCreationException,
    ConcurrentModificationException,
    InvalidLoanDurationException,
    InvalidLoanExtensionException,
    InvalidLoanIdException,
    InvalidLoanReferenceException,
    InvalidLoanReturnDateException,
    InvalidLoanStateException,
    InvalidCancellationReasonException,
    InvalidReservationIdException,
    InvalidReservationGenerationException,
    LoanAlreadyReturnedException,
    LoanNotActiveException,
    LoanNotOverdueException,
    LoanNotFoundException,
    PatronBorrowingLimitReachedException,
    PatronNotEligibleForLoanException,
    ReservationCorrelationMismatchException,
)
from .interfaces import ILoanCommandRepository
from .value_objects import (
    BorrowingTerms,
    DueDate,
    LendingPolicy,
    LoanId,
    LoanStatus,
    ReservationId,
)

__all__ = [
    "Loan",
    "LoanId",
    "ReservationId",
    "DueDate",
    "LoanStatus",
    "BorrowingTerms",
    "LendingPolicy",
    "LoanCreated",
    "LoanCompleted",
    "LoanCancelled",
    "LoanExtended",
    "BookOverdue",
    "ILoanCommandRepository",
    "InvalidLoanIdException",
    "InvalidLoanDurationException",
    "InvalidLoanExtensionException",
    "InvalidLoanReferenceException",
    "InvalidLoanReturnDateException",
    "InvalidLoanStateException",
    "InvalidCancellationReasonException",
    "InvalidReservationIdException",
    "InvalidReservationGenerationException",
    "LoanAlreadyReturnedException",
    "LoanNotActiveException",
    "LoanNotOverdueException",
    "CannotExtendOverdueLoanException",
    "ConcurrentLoanCreationException",
    "ConcurrentModificationException",
    "PatronBorrowingLimitReachedException",
    "PatronNotEligibleForLoanException",
    "ReservationCorrelationMismatchException",
    "BookNotAvailableException",
    "LoanNotFoundException",
]

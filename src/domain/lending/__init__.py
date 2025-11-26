"""
Lending Bounded Context

This is the CORE DOMAIN - the most important bounded context in the library
system. It handles the lending of books to patrons.

Responsibilities:
- Managing book loans (borrowing and returning)
- Tracking due dates and overdue items
- Enforcing borrowing rules and limits
- Managing holds and reservations

Key Aggregates:
- Loan: Represents an active or completed book loan
- LoanableBook: The Lending context's view of a book (focused on availability)

Ubiquitous Language:
- Loan: The act of lending a book to a patron
- LoanableBook: A book that can be borrowed (references Catalog's book)
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
from .entities.loanable_book import LoanableBook
from .value_objects.lending_vo import LoanId, DueDate, LoanStatus
from .events.lending_events import BookBorrowed, BookReturned, BookOverdue

__all__ = [
    "Loan",
    "LoanableBook",
    "LoanId",
    "DueDate",
    "LoanStatus",
    "BookBorrowed",
    "BookReturned",
    "BookOverdue",
]

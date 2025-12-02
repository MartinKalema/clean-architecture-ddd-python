"""
LoanableBook - The Lending context's view of a book.

This is NOT the same as CatalogBook. In the Lending context, we only care about:
- The book's identity (referenced from Catalog)
- Whether it's available for borrowing
- Current loan status

We don't care about:
- Book metadata (that's Catalog's concern)
- Who the author is (irrelevant for lending)

This separation is the essence of Bounded Contexts - each context has its
own model optimized for its specific needs.
"""
from dataclasses import dataclass
from typing import Optional

from src.domain.lending.exceptions import (
    BookNotAvailableException,
    BookNotCheckedOutException,
)
from src.domain.lending.value_objects import LoanId
from src.domain.shared_kernel import AggregateRoot


@dataclass
class LoanableBook(AggregateRoot):
    """
    A book that can be loaned out.

    This is a local entity in the Lending context that references
    a CatalogBook via catalog_book_id. It tracks availability state
    that the Catalog context doesn't know about.
    """

    catalog_book_id: str  # Reference to Catalog context (not a value object here)
    title: str  # Denormalized for display (could be fetched via ACL)
    is_available: bool = True
    current_loan_id: Optional[str] = None

    def checkout(self, loan_id: LoanId) -> None:
        """Mark the book as checked out."""
        if not self.is_available:
            raise BookNotAvailableException(self.catalog_book_id)
        self.is_available = False
        self.current_loan_id = loan_id.value

    def return_book(self) -> None:
        """Mark the book as returned and available."""
        if self.is_available:
            raise BookNotCheckedOutException(self.catalog_book_id)
        self.is_available = True
        self.current_loan_id = None

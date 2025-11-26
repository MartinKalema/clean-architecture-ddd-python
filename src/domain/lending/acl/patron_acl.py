"""
Anti-Corruption Layer for the Patron bounded context.

This ACL translates between the Patron context's model and the
Lending context's needs. The Lending context needs to know about
borrowers, but in its own terms.
"""
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class BorrowerInfo:
    """
    The Lending context's view of a patron as a borrower.

    We don't call them "Patron" in Lending - they're "Borrowers".
    This is the Ubiquitous Language of the Lending context.
    """

    patron_id: str
    email: str
    name: str
    can_borrow: bool  # Has borrowing privileges
    borrowing_limit: int  # Max books they can borrow
    loan_duration_days: int  # How long they can keep books
    current_loan_count: int  # How many books they currently have


class PatronACL(Protocol):
    """
    Anti-Corruption Layer interface for the Patron context.

    This protocol defines what Lending needs from Patron.
    """

    async def get_borrower_info(self, patron_id: str) -> Optional[BorrowerInfo]:
        """
        Get borrower information for lending purposes.

        This translates from Patron's model to Lending's BorrowerInfo.
        It also checks borrowing eligibility.

        Args:
            patron_id: The patron's ID in the Patron context

        Returns:
            BorrowerInfo with lending-relevant data, or None if not found
        """
        ...

    async def get_borrower_by_email(self, email: str) -> Optional[BorrowerInfo]:
        """
        Find a borrower by their email address.

        Useful for looking up patrons when only email is known.
        """
        ...

    async def can_patron_borrow(self, patron_id: str) -> bool:
        """
        Check if a patron can borrow books.

        Returns False if:
        - Patron doesn't exist
        - Patron is suspended
        - Patron has reached their borrowing limit
        """
        ...

    async def increment_loan_count(self, patron_id: str) -> None:
        """Notify Patron context that a book was borrowed."""
        ...

    async def decrement_loan_count(self, patron_id: str) -> None:
        """Notify Patron context that a book was returned."""
        ...

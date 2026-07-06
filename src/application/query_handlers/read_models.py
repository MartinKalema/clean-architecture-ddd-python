"""
Read models - the query side's output DTOs.

These are denormalized views optimized for display, separate from the
write model (the domain aggregates). They are the data structures that
cross the boundary out of the application layer, so they are defined
once here and shared by the query handlers, the query-repository ports,
and their infrastructure implementations.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class BookReadModel:
    """Read model for Book."""
    id: str
    title: str
    author: str
    is_borrowed: bool
    status: str = "available"
    borrowed_at: Optional[datetime] = None
    return_due_date: Optional[datetime] = None


@dataclass(frozen=True)
class PatronReadModel:
    """Read model for Patron."""
    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    membership_tier: str
    is_suspended: bool
    suspended_reason: Optional[str]
    registered_at: datetime


@dataclass(frozen=True)
class LoanReadModel:
    """Read model for Loan."""
    id: str
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime]
    status: str

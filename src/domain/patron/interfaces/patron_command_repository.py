"""
Command Repository interface for the Patron bounded context.
"""
from typing import List, Optional, Protocol

from src.domain.patron.entities import Patron


class IPatronCommandRepository(Protocol):
    """Command repository interface for Patron aggregates."""

    async def add(self, patron: Patron) -> Patron:
        """Register a new patron."""
        ...

    async def get_by_id(self, patron_id: str) -> Optional[Patron]:
        """Find a patron by ID."""
        ...

    async def get_by_email(self, email: str) -> Optional[Patron]:
        """Find a patron by email address."""
        ...

    async def get_all(self) -> List[Patron]:
        """Get all patrons."""
        ...

    async def update(self, patron: Patron) -> None:
        """Update patron information."""
        ...

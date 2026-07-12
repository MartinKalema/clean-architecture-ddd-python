"""Anti-corruption boundary from Patron into borrowing workflows."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BorrowerProfile:
    """Only Patron facts that Catalog/Lending are allowed to consume."""

    patron_id: str
    email: str
    is_eligible: bool
    membership_tier: str
    ineligible_reason: str | None = None


class IBorrowerDirectory(Protocol):
    async def find_by_email(self, email: str) -> BorrowerProfile | None: ...

    async def get_by_id(self, patron_id: str) -> BorrowerProfile | None: ...

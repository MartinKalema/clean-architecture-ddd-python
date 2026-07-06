"""
Query-repository ports (CQRS read side).

These live in the application layer, not the domain: query repositories
exist to serve views and return application read models, so the domain
has no business knowing about them. (The write-side ports — command
repositories and units of work, which speak in aggregates — remain in
the domain, where they belong.)

Implementations live in infrastructure/adapters/*.
"""
from typing import List, Optional, Protocol

from src.application.query_handlers.read_models import (
    BookReadModel,
    LoanReadModel,
    PatronReadModel,
)


class IBookQueryRepository(Protocol):
    """Read-side port for book queries."""

    async def find_by_id(self, book_id: str) -> Optional[BookReadModel]:
        ...

    async def find_all(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
        author_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BookReadModel]:
        ...

    async def count(
        self,
        only_available: bool = False,
        only_borrowed: bool = False,
    ) -> int:
        ...


class IPatronQueryRepository(Protocol):
    """Read-side port for patron queries."""

    async def find_by_id(self, patron_id: str) -> Optional[PatronReadModel]:
        ...

    async def find_by_email(self, email: str) -> Optional[PatronReadModel]:
        ...

    async def find_all(
        self,
        only_suspended: bool = False,
        membership_tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[PatronReadModel]:
        ...

    async def count(self, only_suspended: bool = False) -> int:
        ...


class ILoanQueryRepository(Protocol):
    """Read-side port for loan queries."""

    async def find_by_id(self, loan_id: str) -> Optional[LoanReadModel]:
        ...

    async def find_by_patron(
        self,
        patron_id: str,
        only_active: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LoanReadModel]:
        ...

    async def find_overdue(self, limit: int = 100) -> List[LoanReadModel]:
        ...

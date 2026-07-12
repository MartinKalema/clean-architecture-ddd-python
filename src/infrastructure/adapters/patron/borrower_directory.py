"""Translate authoritative Patron rows into the borrowing-context contract."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.application.ports import BorrowerProfile
from src.infrastructure.adapters.patron.patron_model import PatronModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class PatronBorrowerDirectoryAdapter:
    """Anti-corruption adapter; no Patron DTO or stale projection crosses."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def find_by_email(self, email: str) -> BorrowerProfile | None:
        normalized_email = str(email).strip().lower()
        async with self._session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.email == normalized_email)
            )
            return self._translate(result.scalar_one_or_none())

    async def get_by_id(self, patron_id: str) -> BorrowerProfile | None:
        normalized_id = str(patron_id).strip()
        async with self._session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.id == normalized_id)
            )
            return self._translate(result.scalar_one_or_none())

    @staticmethod
    def _translate(
        patron: PatronModel | None,
    ) -> BorrowerProfile | None:
        if patron is None:
            return None
        suspended = bool(patron.is_suspended)
        return BorrowerProfile(
            patron_id=patron.id,
            email=patron.email,
            is_eligible=not suspended,
            membership_tier=patron.membership_tier,
            ineligible_reason="patron is suspended" if suspended else None,
        )

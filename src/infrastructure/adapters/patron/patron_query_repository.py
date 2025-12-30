"""
Patron Query Repository - CQRS Read Side Implementation.

Implements: IPatronQueryRepository
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.adapters.patron.patron_command_repository import PatronModel


class PatronQueryRepository:
    """Read-optimized repository for Patron queries."""

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def find_by_id(self, patron_id: str) -> Optional[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.id == patron_id)
            )
            patron = result.scalar_one_or_none()
            if not patron:
                return None
            return self._to_read_model(patron)

    async def find_by_email(self, email: str) -> Optional[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.email == email)
            )
            patron = result.scalar_one_or_none()
            if not patron:
                return None
            return self._to_read_model(patron)

    async def find_all(
        self,
        only_suspended: bool = False,
        membership_tier: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        async with self._session_factory() as session:
            stmt = select(PatronModel)

            if only_suspended:
                stmt = stmt.where(PatronModel.is_suspended.is_(True))
            if membership_tier:
                stmt = stmt.where(PatronModel.membership_tier == membership_tier)

            stmt = stmt.offset(offset).limit(limit).order_by(PatronModel.last_name)

            result = await session.execute(stmt)
            patrons = result.scalars().all()
            return [self._to_read_model(p) for p in patrons]

    async def count(self, only_suspended: bool = False) -> int:
        async with self._session_factory() as session:
            stmt = select(func.count(PatronModel.id))
            if only_suspended:
                stmt = stmt.where(PatronModel.is_suspended.is_(True))
            result = await session.execute(stmt)
            return result.scalar_one()

    def _to_read_model(self, patron: PatronModel) -> dict:
        return {
            "id": patron.id,
            "first_name": patron.first_name,
            "last_name": patron.last_name,
            "name": f"{patron.first_name} {patron.last_name}",
            "email": patron.email,
            "membership_tier": patron.membership_tier,
            "is_suspended": patron.is_suspended,
            "suspended_reason": patron.suspended_reason,
            "registered_at": patron.registered_at,
        }

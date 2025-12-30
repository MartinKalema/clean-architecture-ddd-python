"""
Loan Query Repository - CQRS Read Side Implementation.

Implements: ILoanQueryRepository
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.infrastructure.adapters.lending.loan_command_repository import LoanModel


class LoanQueryRepository:
    """Read-optimized repository for Loan queries."""

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def find_by_id(self, loan_id: str) -> Optional[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(LoanModel).where(LoanModel.id == loan_id)
            )
            loan = result.scalar_one_or_none()
            if not loan:
                return None
            return self._to_read_model(loan)

    async def find_by_patron(
        self,
        patron_id: str,
        only_active: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        async with self._session_factory() as session:
            stmt = select(LoanModel).where(LoanModel.patron_id == patron_id)

            if only_active:
                stmt = stmt.where(LoanModel.status == "active")

            stmt = stmt.offset(offset).limit(limit).order_by(LoanModel.borrowed_at.desc())

            result = await session.execute(stmt)
            loans = result.scalars().all()
            return [self._to_read_model(l) for l in loans]

    async def find_overdue(self, limit: int = 100) -> List[dict]:
        async with self._session_factory() as session:
            stmt = (
                select(LoanModel)
                .where(LoanModel.status == "overdue")
                .limit(limit)
                .order_by(LoanModel.due_date)
            )
            result = await session.execute(stmt)
            loans = result.scalars().all()
            return [self._to_read_model(l) for l in loans]

    def _to_read_model(self, loan: LoanModel) -> dict:
        return {
            "id": loan.id,
            "patron_id": loan.patron_id,
            "patron_email": loan.patron_email,
            "catalog_book_id": loan.catalog_book_id,
            "book_title": loan.book_title,
            "borrowed_at": loan.borrowed_at,
            "due_date": loan.due_date,
            "returned_at": loan.returned_at,
            "status": loan.status,
        }

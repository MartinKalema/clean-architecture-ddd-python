from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.lending.interfaces.patron_service import BorrowerInfo
from src.domain.patron.value_objects import MembershipTier
from src.domain.patron.value_objects import MembershipTier
from src.infrastructure.adapters.repositories.patron_command_repository import PatronModel


class PatronQueryRepository:
    """
    SQLAlchemy implementation of Patron Query Repository.
    
    Optimized for Read-Only operations.
    Returns DTOs (BorrowerInfo) directly where possible, avoiding overhead of partial Aggregate reconstruction.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def get_borrower_info(self, patron_id: str) -> Optional[BorrowerInfo]:
        """Fetch borrower info directly from DB model."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.id == patron_id)
            )
            model = result.scalars().first()
            if not model:
                return None
            
            # Map directly to DTO using Domain Logic for limits
            try:
                tier = MembershipTier(model.membership_tier)
                limit = tier.borrowing_limit
                days = tier.loan_duration_days
            except ValueError:
                # Fallback if DB has invalid tier, default to Regular
                tier = MembershipTier.REGULAR
                limit = tier.borrowing_limit
                days = tier.loan_duration_days
            
            return BorrowerInfo(
                patron_id=model.id,
                email=model.email,
                name=f"{model.first_name} {model.last_name}",
                can_borrow=not model.is_suspended and model.active_loans < limit,
                borrowing_limit=limit,
                loan_duration_days=days,
                current_loan_count=model.active_loans
            )

    async def get_borrower_by_email(self, email: str) -> Optional[BorrowerInfo]:
        """Fetch borrower info by email."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(PatronModel).where(PatronModel.email == email)
            )
            model = result.scalars().first()
            if not model:
                return None

            try:
                tier = MembershipTier(model.membership_tier)
                limit = tier.borrowing_limit
                days = tier.loan_duration_days
            except ValueError:
                tier = MembershipTier.REGULAR
                limit = tier.borrowing_limit
                days = tier.loan_duration_days

            return BorrowerInfo(
                patron_id=model.id,
                email=model.email,
                name=f"{model.first_name} {model.last_name}",
                can_borrow=not model.is_suspended and model.active_loans < limit,
                borrowing_limit=limit,
                loan_duration_days=days,
                current_loan_count=model.active_loans
            )

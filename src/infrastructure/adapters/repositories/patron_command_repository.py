from typing import Optional

from sqlalchemy import Column, String, Boolean, DateTime, select, Integer
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.patron.entities.patron import Patron
from src.domain.patron.value_objects import PatronId, PatronName, MembershipTier
from src.domain.shared_kernel import EmailAddress
from src.infrastructure.external.database import Base


class PatronModel(Base):
    """SQLAlchemy model for Patron aggregate."""
    __tablename__ = "patrons"

    id = Column(String, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, unique=True, index=True)
    membership_tier = Column(String, default=MembershipTier.REGULAR.value)
    is_suspended = Column(Boolean, default=False)
    suspended_reason = Column(String, nullable=True)
    active_loans = Column(Integer, default=0)
    registered_at = Column(DateTime)

    def to_entity(self) -> Patron:
        return Patron(
            id=PatronId(self.id),
            name=PatronName(first_name=self.first_name, last_name=self.last_name),
            email=EmailAddress(self.email),
            membership_tier=MembershipTier(self.membership_tier),
            is_suspended=self.is_suspended,
            suspended_reason=self.suspended_reason,
            active_loans=self.active_loans,
            registered_at=self.registered_at
        )

    @staticmethod
    def from_entity(patron: Patron) -> "PatronModel":
        return PatronModel(
            id=patron.id.value,
            first_name=patron.name.first_name,
            last_name=patron.name.last_name,
            email=patron.email.value,
            membership_tier=patron.membership_tier.value,
            is_suspended=patron.is_suspended,
            suspended_reason=patron.suspended_reason,
            active_loans=patron.active_loans,
            registered_at=patron.registered_at
        )


class PatronCommandRepository:
    """SQLAlchemy implementation of Patron Command Repository."""

    """SQLAlchemy implementation of Patron Command Repository."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, patron_id: str) -> Optional[Patron]:
        result = await self._session.execute(
            select(PatronModel).where(PatronModel.id == patron_id)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    async def get_by_email(self, email: str) -> Optional[Patron]:
        result = await self._session.execute(
            select(PatronModel).where(PatronModel.email == email)
        )
        model = result.scalars().first()
        return model.to_entity() if model else None

    async def save(self, patron: Patron) -> None:
        model = PatronModel.from_entity(patron)
        await self._session.merge(model)
        # Commit is handled by UnitOfWork

"""
SQLAlchemy model for Patron bounded context.

Shared between command and query repositories.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String

from src.domain.patron import Patron
from src.domain.patron.value_objects import MembershipTier, PatronId, PatronName
from src.domain.shared_kernel import EmailAddress
from src.infrastructure.external.postgresql import Base


class PatronModel(Base):
    """SQLAlchemy model for Patron aggregate."""

    __tablename__ = "patrons"

    id = Column(String, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    membership_tier = Column(String, default="regular")
    is_suspended = Column(Boolean, default=False)
    suspended_reason = Column(String, nullable=True)
    registered_at = Column(DateTime, nullable=False)
    current_loan_count = Column(Integer, default=0)
    version = Column(String, default="0", nullable=False)

    def to_entity(self) -> Patron:
        """Convert DB model to domain entity."""
        patron = Patron(
            id=PatronId(self.id),
            name=PatronName(first_name=self.first_name, last_name=self.last_name),
            email=EmailAddress(self.email),
            membership_tier=MembershipTier(self.membership_tier),
            is_suspended=self.is_suspended,
            suspended_reason=self.suspended_reason,
            registered_at=self.registered_at,
        )
        patron._version = int(self.version)
        return patron

    @staticmethod
    def from_entity(patron: Patron) -> "PatronModel":
        """Convert domain entity to DB model."""
        return PatronModel(
            id=patron.id.value,
            first_name=patron.name.first_name,
            last_name=patron.name.last_name,
            email=patron.email.value,
            membership_tier=patron.membership_tier.value,
            is_suspended=patron.is_suspended,
            suspended_reason=patron.suspended_reason,
            registered_at=patron.registered_at,
            version=str(patron.version),
        )

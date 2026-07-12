"""
SQLAlchemy model for Patron bounded context.

Shared between command and query repositories.
"""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, Integer, String

from src.domain.patron import Patron
from src.domain.patron.value_objects import MembershipTier, PatronId, PatronName
from src.domain.shared_kernel import EmailAddress
from src.infrastructure.external.postgresql import Base


class PatronModel(Base):
    """SQLAlchemy model for Patron aggregate."""

    __tablename__ = "patrons"
    __table_args__ = (
        Index("ix_patrons_registered_at_id", "registered_at", "id"),
        Index("ix_patrons_is_suspended", "is_suspended"),
        Index("ix_patrons_membership_tier", "membership_tier"),
        CheckConstraint(
            "membership_tier IN ('regular', 'premium', 'researcher')",
            name="ck_patrons_membership_tier",
        ),
        CheckConstraint(
            "id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'", name="ck_patrons_id"
        ),
        CheckConstraint("version >= 0", name="ck_patrons_version"),
        CheckConstraint(
            "length(trim(first_name)) BETWEEN 1 AND 100",
            name="ck_patrons_first_name",
        ),
        CheckConstraint(
            "length(trim(last_name)) BETWEEN 1 AND 100",
            name="ck_patrons_last_name",
        ),
        CheckConstraint("email = lower(trim(email))", name="ck_patrons_email_normalized"),
        CheckConstraint(
            "length(email) BETWEEN 3 AND 254", name="ck_patrons_email_length"
        ),
        CheckConstraint(
            "email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'",
            name="ck_patrons_email_format",
        ),
        CheckConstraint(
            "(is_suspended AND suspended_reason IS NOT NULL AND "
            "length(trim(suspended_reason)) BETWEEN 1 AND 500) "
            "OR (NOT is_suspended AND suspended_reason IS NULL)",
            name="ck_patrons_suspension_state",
        ),
    )

    id = Column(String(64), primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(254), unique=True, index=True, nullable=False)
    membership_tier = Column(String(16), default="regular", nullable=False)
    is_suspended = Column(Boolean, default=False, nullable=False)
    suspended_reason = Column(String(500), nullable=True)
    registered_at = Column(DateTime(timezone=True), nullable=False)
    version = Column(Integer, default=0, nullable=False)

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
        patron._version = self.version
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
            version=patron.version,
        )

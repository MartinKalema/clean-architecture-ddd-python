"""
SQLAlchemy model for Lending bounded context.

Shared between command and query repositories.
"""
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, text

from src.domain.lending import Loan
from src.domain.lending.value_objects import DueDate, LoanId, LoanStatus, ReservationId
from src.infrastructure.external.postgresql import Base


class LoanModel(Base):
    """SQLAlchemy model for Loan aggregate."""

    __tablename__ = "loans"
    __table_args__ = (
        Index("ix_loans_patron_id_status", "patron_id", "status"),
        Index("ix_loans_catalog_book_id_status", "catalog_book_id", "status"),
        Index(
            "ix_loans_outstanding_due_date_id",
            "due_date",
            "id",
            postgresql_where=text("status NOT IN ('returned', 'cancelled')"),
            sqlite_where=text("status NOT IN ('returned', 'cancelled')"),
        ),
        Index(
            "ix_loans_patron_borrowed_id",
            "patron_id",
            text("borrowed_at DESC"),
            "id",
        ),
        Index(
            "ix_loans_reservation_id_unique",
            "reservation_id",
            unique=True,
        ),
        CheckConstraint(
            "status IN ('active', 'returned', 'overdue', 'lost', 'cancelled')",
            name="ck_loans_status",
        ),
        CheckConstraint(
            "reservation_generation >= 1", name="ck_loans_reservation_generation"
        ),
        CheckConstraint(
            "id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'", name="ck_loans_id"
        ),
        CheckConstraint(
            "patron_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_loans_patron_id",
        ),
        CheckConstraint(
            "catalog_book_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_loans_catalog_book_id",
        ),
        CheckConstraint(
            "reservation_id ~* "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_loans_reservation_id",
        ),
        CheckConstraint("version >= 0", name="ck_loans_version"),
        CheckConstraint("due_date > borrowed_at", name="ck_loans_due_after_borrow"),
        CheckConstraint(
            "returned_at IS NULL OR returned_at >= borrowed_at",
            name="ck_loans_return_after_borrow",
        ),
        CheckConstraint(
            "(status = 'returned' AND returned_at IS NOT NULL) OR "
            "(status <> 'returned' AND returned_at IS NULL)",
            name="ck_loans_returned_state",
        ),
        CheckConstraint(
            "patron_email = lower(trim(patron_email)) AND "
            "length(patron_email) BETWEEN 3 AND 254 AND "
            "patron_email ~ "
            "'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}$'",
            name="ck_loans_patron_email",
        ),
        CheckConstraint(
            "length(trim(book_title)) BETWEEN 1 AND 100",
            name="ck_loans_book_title",
        ),
        Index(
            "ix_loans_outstanding_book_unique",
            "catalog_book_id",
            unique=True,
            postgresql_where=text("status NOT IN ('returned', 'cancelled')"),
            sqlite_where=text("status NOT IN ('returned', 'cancelled')"),
        ),
    )

    id = Column(String(64), primary_key=True)
    patron_id = Column(String(64), index=True, nullable=False)
    patron_email = Column(String(254), nullable=False)
    catalog_book_id = Column(String(64), index=True, nullable=False)
    reservation_id = Column(String(36), nullable=False)
    reservation_generation = Column(Integer, nullable=False)
    book_title = Column(String(100), nullable=False)
    borrowed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    due_date = Column(DateTime(timezone=True), nullable=False, index=True)
    returned_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), default="active", nullable=False, index=True)
    version = Column(Integer, default=0, nullable=False)

    def to_entity(self) -> Loan:
        """Convert DB model to domain entity."""
        loan = Loan(
            id=LoanId(self.id),
            patron_id=self.patron_id,
            patron_email=self.patron_email,
            catalog_book_id=self.catalog_book_id,
            reservation_id=ReservationId(self.reservation_id),
            reservation_generation=self.reservation_generation,
            book_title=self.book_title,
            due_date=DueDate(self.due_date),
            borrowed_at=self.borrowed_at,
            status=LoanStatus(self.status),
            returned_at=self.returned_at,
        )
        loan._version = self.version
        return loan

    @staticmethod
    def from_entity(loan: Loan) -> "LoanModel":
        """Convert domain entity to DB model."""
        return LoanModel(
            id=loan.id.value,
            patron_id=loan.patron_id,
            patron_email=loan.patron_email,
            catalog_book_id=loan.catalog_book_id,
            reservation_id=loan.reservation_id.value,
            reservation_generation=loan.reservation_generation,
            book_title=loan.book_title,
            borrowed_at=loan.borrowed_at,
            due_date=loan.due_date.value,
            returned_at=loan.returned_at,
            status=loan.status.value,
            version=loan.version,
        )

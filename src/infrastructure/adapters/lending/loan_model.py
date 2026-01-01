"""
SQLAlchemy model for Lending bounded context.

Shared between command and query repositories.
"""
from sqlalchemy import Column, DateTime, String

from src.domain.lending import Loan
from src.domain.lending.value_objects import DueDate, LoanId, LoanStatus
from src.infrastructure.external.postgresql import Base


class LoanModel(Base):
    """SQLAlchemy model for Loan aggregate."""

    __tablename__ = "loans"

    id = Column(String, primary_key=True, index=True)
    patron_id = Column(String, index=True, nullable=False)
    patron_email = Column(String, nullable=False)
    catalog_book_id = Column(String, index=True, nullable=False)
    book_title = Column(String, nullable=False)
    borrowed_at = Column(DateTime, nullable=False)
    due_date = Column(DateTime, nullable=False)
    returned_at = Column(DateTime, nullable=True)
    status = Column(String, default="active", nullable=False)
    version = Column(String, default="0", nullable=False)

    def to_entity(self) -> Loan:
        """Convert DB model to domain entity."""
        loan = Loan(
            id=LoanId(self.id),
            patron_id=self.patron_id,
            patron_email=self.patron_email,
            catalog_book_id=self.catalog_book_id,
            book_title=self.book_title,
            due_date=DueDate(self.due_date),
            borrowed_at=self.borrowed_at,
            status=LoanStatus(self.status),
            returned_at=self.returned_at,
        )
        loan._version = int(self.version)
        return loan

    @staticmethod
    def from_entity(loan: Loan) -> "LoanModel":
        """Convert domain entity to DB model."""
        return LoanModel(
            id=loan.id.value,
            patron_id=loan.patron_id,
            patron_email=loan.patron_email,
            catalog_book_id=loan.catalog_book_id,
            book_title=loan.book_title,
            borrowed_at=loan.borrowed_at,
            due_date=loan.due_date.value,
            returned_at=loan.returned_at,
            status=loan.status.value,
            version=str(loan.version),
        )

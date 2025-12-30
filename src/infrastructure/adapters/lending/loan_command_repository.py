"""
Loan Command Repository - Infrastructure implementation.

Implements: ILoanCommandRepository
"""
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, String, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.lending import Loan
from src.domain.lending.exceptions import LendingException
from src.domain.lending.value_objects import DueDate, LoanId, LoanStatus
from src.infrastructure.exceptions import DatabaseException
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


class ConcurrentModificationException(LendingException):
    """Raised when optimistic locking fails."""
    def __init__(self, loan_id: str):
        super().__init__(f"Loan {loan_id} was modified by another process")


class LoanCommandRepository:
    """Repository implementation for Loan aggregate."""

    def __init__(self, session: AsyncSession, identity_map: Optional[Dict[str, Loan]] = None):
        self.session = session
        self.identity_map = identity_map if identity_map is not None else {}

    async def add(self, loan: Loan) -> Loan:
        try:
            db_loan = LoanModel.from_entity(loan)
            self.session.add(db_loan)
            self.identity_map[loan.id.value] = loan
            return loan
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error adding loan: {str(e)}", original_exception=e)

    async def get_by_id(self, loan_id: str) -> Optional[Loan]:
        try:
            if loan_id in self.identity_map:
                return self.identity_map[loan_id]

            result = await self.session.execute(
                select(LoanModel).where(LoanModel.id == loan_id)
            )
            db_loan = result.scalar_one_or_none()
            if db_loan:
                entity = db_loan.to_entity()
                self.identity_map[entity.id.value] = entity
                return entity
            return None
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving loan {loan_id}: {str(e)}", original_exception=e)

    async def get_active_loans_for_patron(self, patron_id: str) -> List[Loan]:
        try:
            result = await self.session.execute(
                select(LoanModel)
                .where(LoanModel.patron_id == patron_id)
                .where(LoanModel.status == LoanStatus.ACTIVE.value)
            )
            db_loans = result.scalars().all()
            entities = []
            for db_loan in db_loans:
                if db_loan.id in self.identity_map:
                    entities.append(self.identity_map[db_loan.id])
                else:
                    entity = db_loan.to_entity()
                    self.identity_map[entity.id.value] = entity
                    entities.append(entity)
            return entities
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving loans for patron: {str(e)}", original_exception=e)

    async def get_active_loan_for_book(self, catalog_book_id: str) -> Optional[Loan]:
        try:
            result = await self.session.execute(
                select(LoanModel)
                .where(LoanModel.catalog_book_id == catalog_book_id)
                .where(LoanModel.status == LoanStatus.ACTIVE.value)
            )
            db_loan = result.scalar_one_or_none()
            if db_loan:
                if db_loan.id in self.identity_map:
                    return self.identity_map[db_loan.id]
                entity = db_loan.to_entity()
                self.identity_map[entity.id.value] = entity
                return entity
            return None
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving loan for book: {str(e)}", original_exception=e)

    async def update(self, loan: Loan) -> None:
        try:
            expected_version = loan.version
            new_version = expected_version + 1

            result = await self.session.execute(
                update(LoanModel)
                .where(LoanModel.id == loan.id.value)
                .where(LoanModel.version == str(expected_version))
                .values(
                    status=loan.status.value,
                    returned_at=loan.returned_at,
                    due_date=loan.due_date.value,
                    version=str(new_version),
                )
            )

            if result.rowcount == 0:
                check_result = await self.session.execute(
                    select(LoanModel).where(LoanModel.id == loan.id.value)
                )
                if check_result.scalar_one_or_none() is None:
                    raise DatabaseException(f"Loan {loan.id.value} not found")
                else:
                    raise ConcurrentModificationException(loan.id.value)

            loan._version = new_version
            self.identity_map[loan.id.value] = loan

        except ConcurrentModificationException:
            raise
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error updating loan: {str(e)}", original_exception=e)

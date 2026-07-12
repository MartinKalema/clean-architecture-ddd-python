"""SQLAlchemy process-state repository for borrow operations."""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.exceptions import (
    BorrowOperationNotFoundException,
    BorrowOperationTransitionException,
)
from src.application.ports import (
    BorrowOperation,
    BorrowOperationStatus,
)
from src.infrastructure.adapters.application_state.models import BorrowOperationModel


class BorrowOperationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, operation: BorrowOperation) -> None:
        self._session.add(
            BorrowOperationModel(
                operation_id=operation.operation_id,
                book_id=operation.book_id,
                patron_id=operation.patron_id,
                reservation_generation=operation.reservation_generation,
                status=operation.status.value,
                loan_id=operation.loan_id,
                failure_reason=operation.failure_reason,
                created_at=operation.created_at,
                updated_at=operation.updated_at,
            )
        )

    async def get(self, operation_id: str) -> BorrowOperation | None:
        result = await self._session.execute(
            select(BorrowOperationModel).where(
                BorrowOperationModel.operation_id == operation_id
            )
        )
        row = result.scalar_one_or_none()
        return self._to_operation(row) if row else None

    async def transition(
        self,
        operation_id: str,
        status: BorrowOperationStatus,
        *,
        book_id: str,
        patron_id: str,
        reservation_generation: int,
        loan_id: str | None = None,
        failure_reason: str | None = None,
        updated_at: datetime,
    ) -> None:
        allowed_sources = {
            BorrowOperationStatus.BORROWED: (BorrowOperationStatus.RESERVED.value,),
            BorrowOperationStatus.RELEASED: (BorrowOperationStatus.RESERVED.value,),
            BorrowOperationStatus.RETURNED: (BorrowOperationStatus.BORROWED.value,),
        }
        if status not in allowed_sources:
            raise BorrowOperationTransitionException(
                operation_id, f"{status.value} is not a transition target"
            )
        result = await self._session.execute(
            update(BorrowOperationModel)
            .where(BorrowOperationModel.operation_id == operation_id)
            .where(BorrowOperationModel.book_id == book_id)
            .where(BorrowOperationModel.patron_id == patron_id)
            .where(
                BorrowOperationModel.reservation_generation
                == reservation_generation
            )
            .where(BorrowOperationModel.status.in_(allowed_sources[status]))
            .values(
                status=status.value,
                loan_id=loan_id,
                failure_reason=failure_reason,
                updated_at=updated_at,
            )
        )
        if result.rowcount == 0:
            current = await self.get(operation_id)
            if current is None:
                raise BorrowOperationNotFoundException(operation_id)
            raise BorrowOperationTransitionException(
                operation_id,
                "identity, fencing generation, or current status does not match",
            )

    @staticmethod
    def _to_operation(row: BorrowOperationModel) -> BorrowOperation:
        return BorrowOperation(
            operation_id=row.operation_id,
            book_id=row.book_id,
            patron_id=row.patron_id,
            reservation_generation=row.reservation_generation,
            status=BorrowOperationStatus(row.status),
            loan_id=row.loan_id,
            failure_reason=row.failure_reason,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

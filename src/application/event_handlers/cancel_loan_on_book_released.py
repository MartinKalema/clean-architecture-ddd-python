"""Cancel the matching Lending loan when Catalog releases a reservation."""
from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.command_handlers.cancel_loan import (
    CancelLoanCommand,
)

if TYPE_CHECKING:
    from src.application.ports import ICommandHandler, ILogger
    from src.domain.catalog import CatalogBookReleased


class CancelLoanOnBookReleasedHandler:
    """Compensates only the loan belonging to the released reservation."""

    inbox_consumer_name = "lending.cancel-loan-on-catalog-released.v1"

    def __init__(
        self,
        cancel_loan_operation: ICommandHandler[CancelLoanCommand, bool],
        logger: ILogger,
    ):
        self._cancel_loan = cancel_loan_operation
        self.logger = logger

    async def handle(self, event: CatalogBookReleased) -> None:
        changed = await self._cancel_loan.handle(
            CancelLoanCommand(
                reservation_id=event.reservation_id,
                reservation_generation=event.reservation_generation,
                patron_id=event.patron_id,
                catalog_book_id=event.book_id,
                # Catalog releases only RESERVED state, before it records the
                # loan id. The reservation UUID is unique in Lending.
                expected_loan_id=None,
                reason=event.reason,
            )
        )
        if not changed:
            self.logger.info(
                f"Catalog release for reservation {event.reservation_id} "
                f"required no Lending change"
            )

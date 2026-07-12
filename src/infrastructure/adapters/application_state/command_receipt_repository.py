"""SQLAlchemy implementation of durable command receipts."""
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports import CommandReceipt
from src.infrastructure.adapters.application_state.models import CommandReceiptModel


class CommandReceiptRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
        self.pending: list[CommandReceipt] = []

    async def get(self, scope: str, idempotency_key: str) -> CommandReceipt | None:
        result = await self._session.execute(
            select(CommandReceiptModel).where(
                CommandReceiptModel.scope == scope,
                CommandReceiptModel.idempotency_key == idempotency_key,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return CommandReceipt(
            scope=row.scope,
            idempotency_key=row.idempotency_key,
            request_hash=row.request_hash,
            response=json.loads(row.response_payload),
            created_at=row.created_at,
        )

    async def add(self, receipt: CommandReceipt) -> None:
        values = {
            "scope": receipt.scope,
            "idempotency_key": receipt.idempotency_key,
            "request_hash": receipt.request_hash,
            "response_payload": json.dumps(
                receipt.response,
                default=_json_default,
                sort_keys=True,
            ),
        }
        # Omission lets the database's UTC server default run; explicitly
        # assigning None would violate the non-null column instead.
        if receipt.created_at is not None:
            values["created_at"] = receipt.created_at
        self._session.add(CommandReceiptModel(**values))
        self.pending.append(receipt)


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported receipt value: {type(value).__name__}")

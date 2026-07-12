"""Bound durable application/delivery state using database-owned time."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DurableStateRetentionService:
    """Prune only state older than its documented replay/business horizon."""

    _POLICIES = {
        "command_receipts": ("created_at", None),
        "borrow_operations": (
            "updated_at",
            "status IN ('released', 'returned')",
        ),
        "event_inbox": ("processed_at", "status = 'processed'"),
        "event_quarantine": ("last_seen_at", None),
    }

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def prune(
        self,
        *,
        command_receipt_days: int = 30,
        terminal_operation_days: int = 120,
        processed_inbox_days: int = 120,
        quarantine_days: int = 365,
        batch_size: int = 500,
        max_batches_per_table: int = 20,
    ) -> dict[str, int]:
        horizons = {
            "command_receipts": command_receipt_days,
            "borrow_operations": terminal_operation_days,
            "event_inbox": processed_inbox_days,
            "event_quarantine": quarantine_days,
        }
        if any(not 1 <= days <= 3650 for days in horizons.values()):
            raise ValueError("retention days must be between 1 and 3650")
        if not 1 <= batch_size <= 10_000:
            raise ValueError("batch_size must be between 1 and 10000")
        if not 1 <= max_batches_per_table <= 10_000:
            raise ValueError("max_batches_per_table must be between 1 and 10000")

        deleted: dict[str, int] = {}
        for table_name, days in horizons.items():
            deleted[table_name] = await self._prune_table(
                table_name=table_name,
                retention_days=days,
                batch_size=batch_size,
                max_batches=max_batches_per_table,
            )
        return deleted

    async def _prune_table(
        self,
        *,
        table_name: str,
        retention_days: int,
        batch_size: int,
        max_batches: int,
    ) -> int:
        timestamp_column, extra_predicate = self._POLICIES[table_name]
        predicate = f" AND {extra_predicate}" if extra_predicate else ""
        statement = text(
            f"""
            WITH candidates AS (
                SELECT ctid
                  FROM {table_name}
                 WHERE {timestamp_column} < clock_timestamp()
                       - make_interval(days => :retention_days)
                       {predicate}
                 ORDER BY {timestamp_column}
                 LIMIT :batch_size
                 FOR UPDATE SKIP LOCKED
            )
            DELETE FROM {table_name}
             WHERE ctid IN (SELECT ctid FROM candidates)
            """
        )
        total = 0
        for _ in range(max_batches):
            async with self._session_factory() as session:
                if session.get_bind().dialect.name != "postgresql":
                    raise RuntimeError("Durable-state retention requires PostgreSQL")
                async with session.begin():
                    result = await session.execute(
                        statement,
                        {
                            "retention_days": retention_days,
                            "batch_size": batch_size,
                        },
                    )
                    count = result.rowcount or 0
                    total += count
            if count < batch_size:
                break
        return total

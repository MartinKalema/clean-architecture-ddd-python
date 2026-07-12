"""Bounded retention for append-only Debezium outbox rows."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .outbox_model import OutboxMessageModel


class OutboxRetentionService:
    """Delete old rows in small committed batches to bound locks and WAL."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    async def prune(
        self,
        *,
        older_than: datetime | None = None,
        retention_hours: int | None = None,
        batch_size: int = 500,
        max_batches: int = 20,
        replication_slot: str | None = None,
        max_slot_lag_bytes: int = 1_073_741_824,
    ) -> int:
        if not 1 <= batch_size <= 10_000:
            raise ValueError("batch_size must be between 1 and 10000")
        if not 1 <= max_batches <= 10_000:
            raise ValueError("max_batches must be between 1 and 10000")
        if (older_than is None) == (retention_hours is None):
            raise ValueError("provide exactly one of older_than or retention_hours")
        if older_than is not None and (
            older_than.tzinfo is None or older_than.utcoffset() is None
        ):
            raise ValueError("older_than must be timezone-aware")
        if retention_hours is not None and retention_hours < 1:
            raise ValueError("retention_hours must be positive")
        if max_slot_lag_bytes < 0:
            raise ValueError("max_slot_lag_bytes must be non-negative")
        if replication_slot is not None and (
            re.fullmatch(r"[a-z][a-z0-9_]{0,62}", replication_slot) is None
        ):
            raise ValueError("replication_slot has an invalid PostgreSQL identifier")

        explicit_cutoff = (
            older_than.astimezone(timezone.utc)
            if older_than is not None
            else None
        )
        deleted = 0
        for _ in range(max_batches):
            async with self._session_factory() as session:
                async with session.begin():
                    is_postgresql = session.get_bind().dialect.name == "postgresql"
                    if replication_slot is not None:
                        if not is_postgresql:
                            raise RuntimeError(
                                "Replication-slot fencing requires PostgreSQL"
                            )
                        await self._require_active_replication_slot(
                            session,
                            replication_slot,
                            max_slot_lag_bytes=max_slot_lag_bytes,
                        )
                    if retention_hours is not None:
                        if not is_postgresql:
                            raise RuntimeError(
                                "Database-clock retention requires PostgreSQL"
                            )
                        cutoff = await session.scalar(
                            text(
                                "SELECT clock_timestamp() - "
                                "make_interval(hours => :retention_hours)"
                            ),
                            {"retention_hours": retention_hours},
                        )
                        assert cutoff is not None
                    else:
                        assert explicit_cutoff is not None
                        cutoff = explicit_cutoff
                    result = await session.execute(
                        select(OutboxMessageModel.id)
                        .where(OutboxMessageModel.inserted_at < cutoff)
                        .order_by(
                            OutboxMessageModel.inserted_at,
                            OutboxMessageModel.id,
                        )
                        .limit(batch_size)
                    )
                    message_ids = list(result.scalars())
                    if not message_ids:
                        return deleted
                    await session.execute(
                        delete(OutboxMessageModel).where(
                            OutboxMessageModel.id.in_(message_ids)
                        )
                    )
                    # Slot state is external to this transaction. Recheck after
                    # the delete and raise before commit so a connector stop,
                    # slot replacement, or excessive lag rolls the batch back.
                    if replication_slot is not None:
                        await self._require_active_replication_slot(
                            session,
                            replication_slot,
                            max_slot_lag_bytes=max_slot_lag_bytes,
                        )
                    deleted += len(message_ids)
            if len(message_ids) < batch_size:
                break
        return deleted

    async def _require_active_replication_slot(
        self,
        session: AsyncSession,
        slot_name: str,
        *,
        max_slot_lag_bytes: int,
    ) -> None:
        """Fence pruning on slot identity, activity, and bounded WAL lag."""
        ready = await session.scalar(
            text(
                """
                SELECT active
                   AND confirmed_flush_lsn IS NOT NULL
                   AND pg_wal_lsn_diff(
                       pg_current_wal_lsn(), confirmed_flush_lsn
                   ) <= :max_slot_lag_bytes
                  FROM pg_replication_slots
                 WHERE slot_name = :slot_name
                   AND database = current_database()
                """
            ),
            {
                "slot_name": slot_name,
                "max_slot_lag_bytes": max_slot_lag_bytes,
            },
        )
        if ready is not True:
            raise RuntimeError(
                f"Outbox replication slot {slot_name!r} is absent, inactive, "
                "or beyond the configured WAL-lag limit; retention is fenced off"
            )

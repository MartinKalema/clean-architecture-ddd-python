"""PostgreSQL implementation of the cross-context borrowing-admission fence."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def acquire_borrowing_fence(
    session: AsyncSession,
    patron_id: str,
) -> None:
    """Serialize policy changes and final loan admission for one patron.

    Transaction-scoped advisory locks survive PgBouncer transaction pooling
    and are released automatically on commit/rollback. SQLite remains a test
    adapter and deliberately has no cross-connection advisory-lock analogue.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(patron_id, 0)
            )
        )
    )

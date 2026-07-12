"""Cluster-wide fencing for read-model rebuild jobs."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


# Stable, application-owned PostgreSQL advisory-lock key (ASCII ``CADDREIN``).
# The lock is session scoped, so it remains held across the reindexer's many
# short database transactions and is also released by PostgreSQL if the worker
# process or its connection dies.
READ_MODEL_REINDEX_LOCK_ID = 0x434144445245494E


class ReindexAlreadyRunningError(RuntimeError):
    """Raised when another worker already owns the reindex fence."""


class ReindexLockOwnershipError(RuntimeError):
    """Raised when PostgreSQL reports that this session no longer owns the fence."""


def _annotate(error: BaseException, note: str) -> None:
    """Attach cleanup context without masking the primary failure.

    ``BaseException.add_note`` is only available on Python 3.11+, while this
    project still declares Python 3.10 compatibility.
    """
    add_note = getattr(error, "add_note", None)
    if add_note is not None:
        add_note(note)


@asynccontextmanager
async def read_model_reindex_lock(engine: AsyncEngine) -> AsyncIterator[None]:
    """Hold the cluster-wide reindex fence for the complete rebuild job.

    PostgreSQL advisory locks are connection/session scoped. A dedicated
    pooled connection is therefore checked out until every requested alias is
    rebuilt. The implicit transactions created by the lock/unlock statements
    are committed immediately; the long-running job itself is not left
    idle-in-transaction.
    """
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "Read-model reindex fencing requires PostgreSQL; "
            f"configured dialect is {engine.dialect.name!r}"
        )

    async with engine.connect() as connection:
        acquired = await connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": READ_MODEL_REINDEX_LOCK_ID},
        )
        await connection.commit()
        if acquired is not True:
            raise ReindexAlreadyRunningError(
                "Another read-model reindex job is already running; refusing "
                "to modify dual-write targets or aliases"
            )

        body_error: BaseException | None = None
        try:
            yield
        except BaseException as error:
            body_error = error
            raise
        finally:
            try:
                released = await connection.scalar(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": READ_MODEL_REINDEX_LOCK_ID},
                )
                await connection.commit()
                if released is not True:
                    raise ReindexLockOwnershipError(
                        "PostgreSQL reports that the reindex advisory lock is "
                        "no longer owned by this worker"
                    )
            except BaseException as release_error:
                if body_error is None:
                    raise
                _annotate(
                    body_error,
                    f"Additionally failed to release the reindex fence: {release_error}",
                )

"""Tests for the full-job PostgreSQL reindex fence."""

from types import SimpleNamespace

import pytest

from src.infrastructure.adapters.reindex_lock import (
    READ_MODEL_REINDEX_LOCK_ID,
    ReindexAlreadyRunningError,
    read_model_reindex_lock,
)


class _Connection:
    def __init__(self, results: list[bool], events: list[str]) -> None:
        self._results = iter(results)
        self.events = events

    async def scalar(self, statement, parameters):
        sql = str(statement)
        self.events.append(sql)
        assert parameters == {"lock_id": READ_MODEL_REINDEX_LOCK_ID}
        return next(self._results)

    async def commit(self) -> None:
        self.events.append("commit")


class _ConnectionContext:
    def __init__(self, connection: _Connection, events: list[str]) -> None:
        self.connection = connection
        self.events = events

    async def __aenter__(self) -> _Connection:
        self.events.append("connect")
        return self.connection

    async def __aexit__(self, *_args) -> None:
        self.events.append("disconnect")


class _Engine:
    def __init__(self, results: list[bool], dialect: str = "postgresql") -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self.events: list[str] = []
        self.connection = _Connection(results, self.events)

    def connect(self) -> _ConnectionContext:
        return _ConnectionContext(self.connection, self.events)


@pytest.mark.asyncio
async def test_reindex_lock_fences_the_complete_job_and_releases_afterward():
    engine = _Engine([True, True])

    async with read_model_reindex_lock(engine):
        engine.events.append("all aliases rebuilt")

    assert engine.events == [
        "connect",
        "SELECT pg_try_advisory_lock(:lock_id)",
        "commit",
        "all aliases rebuilt",
        "SELECT pg_advisory_unlock(:lock_id)",
        "commit",
        "disconnect",
    ]


@pytest.mark.asyncio
async def test_reindex_lock_fails_before_work_when_another_job_owns_it():
    engine = _Engine([False])

    with pytest.raises(ReindexAlreadyRunningError, match="already running"):
        async with read_model_reindex_lock(engine):
            pytest.fail("contending worker must not enter the fenced body")

    assert engine.events == [
        "connect",
        "SELECT pg_try_advisory_lock(:lock_id)",
        "commit",
        "disconnect",
    ]


@pytest.mark.asyncio
async def test_reindex_lock_releases_when_rebuild_fails_without_masking_cause():
    engine = _Engine([True, True])

    with pytest.raises(ValueError, match="bulk indexing failed"):
        async with read_model_reindex_lock(engine):
            raise ValueError("bulk indexing failed")

    assert "SELECT pg_advisory_unlock(:lock_id)" in engine.events


@pytest.mark.asyncio
async def test_reindex_lock_rejects_non_postgresql_backends():
    engine = _Engine([], dialect="sqlite")

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        async with read_model_reindex_lock(engine):
            pytest.fail("an in-process fallback would not provide fencing")

    assert engine.events == []

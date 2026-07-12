"""Focused tests for versioned, durable event delivery."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka.structs import TopicPartition
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from scripts.replay_dlq import replay_partition
from src.domain.lending import LoanCreated
from src.domain.shared_kernel import ValidationException
from src.infrastructure.adapters.events import (
    EventDispatcher,
    InboxClaim,
    InboxClaimStatus,
    InboxMessageModel,
    InvalidEventEnvelopeError,
    QuarantinedEventModel,
    SqlAlchemyEventQuarantine,
    SqlAlchemyHandlerInbox,
    UnsupportedEventContractError,
    deserialize_event,
    serialize_event,
)
from src.infrastructure.adapters.outbox import (
    OutboxMessageModel,
    OutboxRetentionService,
)
from src.infrastructure.exceptions import EventDispatcherException
from src.infrastructure.external.kafka_client import encode_dead_letter_field


def _loan_created(**metadata) -> LoanCreated:
    values = dict(
        loan_id="loan-1",
        reservation_id="11111111-1111-4111-8111-111111111111",
        reservation_generation=3,
        patron_id="patron-1",
        patron_email="patron@example.com",
        book_id="book-1",
        book_title="Domain-Driven Design",
        borrowed_at=datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc),
        due_date=datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc),
    )
    values.update(metadata)
    return LoanCreated(**values)


def test_namespaced_envelope_round_trip_includes_causation_metadata():
    event = _loan_created(correlation_id="workflow-1", causation_id="reserve-1")

    payload = json.loads(serialize_event(event))

    assert payload["envelope_version"] == 1
    assert payload["contract"] == {
        "namespace": "library.lending",
        "name": "loan-created",
        "version": 1,
    }
    assert payload["metadata"]["correlation_id"] == "workflow-1"
    assert payload["metadata"]["causation_id"] == "reserve-1"
    assert deserialize_event(payload) == event


def test_event_trace_identities_are_bounded_before_outbox_persistence():
    with pytest.raises(ValidationException, match="event_id"):
        _loan_created(event_id="x" * 129)
    with pytest.raises(ValidationException, match="correlation_id"):
        _loan_created(correlation_id="unsafe identity")


def test_flat_payload_is_rejected_instead_of_guessing_an_old_format():
    event = _loan_created()
    flat_payload = {**event.__dict__, "event_type": "LoanCreated"}

    with pytest.raises(InvalidEventEnvelopeError, match="Unexpected event envelope"):
        deserialize_event(json.loads(json.dumps(flat_payload, default=str)))


def test_future_contract_version_is_rejected_for_quarantine():
    payload = json.loads(serialize_event(_loan_created()))
    payload["contract"]["version"] = 999

    with pytest.raises(UnsupportedEventContractError) as exc_info:
        deserialize_event(payload)

    assert exc_info.value.contract_name == "library.lending.loan-created"
    assert exc_info.value.contract_version == 999


def test_non_current_contract_version_is_rejected_for_quarantine():
    payload = json.loads(serialize_event(_loan_created()))
    payload["contract"]["version"] = 0

    with pytest.raises(UnsupportedEventContractError) as exc_info:
        deserialize_event(payload)

    assert exc_info.value.contract_name == "library.lending.loan-created"
    assert exc_info.value.contract_version == 0


def test_known_contract_rejects_wrong_scalar_type():
    payload = json.loads(serialize_event(_loan_created()))
    payload["data"]["reservation_generation"] = True

    with pytest.raises(InvalidEventEnvelopeError, match="must be an integer"):
        deserialize_event(payload)


def test_known_contract_rejects_semantically_invalid_reservation():
    payload = json.loads(serialize_event(_loan_created()))
    payload["data"]["reservation_id"] = "not-a-uuid"

    with pytest.raises(InvalidEventEnvelopeError, match="reservation_id"):
        deserialize_event(payload)


def test_known_contract_rejects_nonpositive_loan_period():
    payload = json.loads(serialize_event(_loan_created()))
    payload["data"]["due_date"] = payload["data"]["borrowed_at"]

    with pytest.raises(InvalidEventEnvelopeError, match="after borrowed_at"):
        deserialize_event(payload)


def test_wire_contract_rejects_ambiguous_naive_datetime():
    payload = json.loads(serialize_event(_loan_created()))
    payload["data"]["borrowed_at"] = "2026-07-04T12:00:00"

    with pytest.raises(InvalidEventEnvelopeError, match="explicit UTC offset"):
        deserialize_event(payload)


@pytest.mark.asyncio
async def test_dispatch_context_propagates_correlation_and_direct_cause():
    source = _loan_created(correlation_id="workflow-1")

    class EmittingHandler:
        emitted = None

        async def handle(self, _event):
            self.emitted = _loan_created(loan_id="loan-2")

    handler = EmittingHandler()
    await EventDispatcher(subscriptions={LoanCreated: [handler]}).dispatch(source)

    assert handler.emitted.correlation_id == "workflow-1"
    assert handler.emitted.causation_id == source.event_id


class _MemoryInbox:
    def __init__(self):
        self.states = {}

    async def claim(self, *, event_id, handler_name, **_metadata):
        if self.states.get((event_id, handler_name)) == "processed":
            return InboxClaim(InboxClaimStatus.PROCESSED)
        token = f"token-{handler_name}"
        self.states[(event_id, handler_name)] = token
        return InboxClaim(InboxClaimStatus.CLAIMED, token)

    async def complete(self, *, event_id, handler_name, token):
        assert self.states[(event_id, handler_name)] == token
        self.states[(event_id, handler_name)] = "processed"

    async def fail(self, *, event_id, handler_name, token, error):
        assert self.states[(event_id, handler_name)] == token
        self.states[(event_id, handler_name)] = "failed"


@pytest.mark.asyncio
async def test_per_handler_inbox_skips_only_the_handler_that_already_succeeded():
    class FailingOnce:
        def __init__(self):
            self.calls = 0

        async def handle(self, _event):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient")

    class Succeeds:
        def __init__(self):
            self.calls = 0

        async def handle(self, _event):
            self.calls += 1

    failing = FailingOnce()
    succeeds = Succeeds()
    dispatcher = EventDispatcher(
        subscriptions={LoanCreated: [failing, succeeds]},
        inbox=_MemoryInbox(),
        logger=MagicMock(),
    )
    event = _loan_created()

    with pytest.raises(EventDispatcherException):
        await dispatcher.dispatch(event)
    await dispatcher.dispatch(event)

    assert failing.calls == 2
    assert succeeds.calls == 1


@pytest.mark.asyncio
async def test_sqlalchemy_inbox_and_quarantine_are_durable_and_deduplicated():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(InboxMessageModel.__table__.create)
        await connection.run_sync(QuarantinedEventModel.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    inbox = SqlAlchemyHandlerInbox(session_factory, lease_seconds=30)

    with pytest.raises(ValueError, match="handler_name"):
        await inbox.claim(
            event_id="event-1",
            handler_name="unsafe handler",
            contract_name="library.lending.loan-created",
            contract_version=1,
            payload_hash="a" * 64,
            correlation_id="workflow-1",
            causation_id=None,
        )

    claim = await inbox.claim(
        event_id="event-1",
        handler_name="handler-1",
        contract_name="library.lending.loan-created",
        contract_version=1,
        payload_hash="a" * 64,
        correlation_id="workflow-1",
        causation_id="reserve-1",
    )
    assert claim.status == InboxClaimStatus.CLAIMED
    await inbox.complete(
        event_id="event-1", handler_name="handler-1", token=claim.token
    )
    replay = await inbox.claim(
        event_id="event-1",
        handler_name="handler-1",
        contract_name="library.lending.loan-created",
        contract_version=1,
        payload_hash="a" * 64,
        correlation_id="workflow-1",
        causation_id="reserve-1",
    )
    assert replay.status == InboxClaimStatus.PROCESSED
    with pytest.raises(RuntimeError, match="Event identity collision"):
        await inbox.claim(
            event_id="event-1",
            handler_name="handler-1",
            contract_name="library.catalog.book-returned",
            contract_version=1,
            payload_hash="b" * 64,
            correlation_id="workflow-1",
            causation_id="reserve-1",
        )

    quarantine = SqlAlchemyEventQuarantine(session_factory)
    kwargs = {
        "topic": "outbox.event.loan",
        "message_key": "loan-1",
        "payload": {"contract": {"version": 999}},
        "reason": "unsupported version",
        "event_id": "event-bad",
        "contract_name": "library.lending.loan-created",
        "contract_version": 999,
    }
    first_id = await quarantine.quarantine(**kwargs)
    second_id = await quarantine.quarantine(**kwargs)
    assert second_id == first_id
    async with session_factory() as session:
        row = await session.get(QuarantinedEventModel, first_id)
        assert row.occurrence_count == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_dlq_replay_scopes_reads_and_commits_to_each_partition():
    first = TopicPartition("events.dlq", 0)
    second = TopicPartition("events.dlq", 1)

    class FakeConsumer:
        def __init__(self):
            self.positions = {first: 0, second: 0}
            self.records = {
                first: [SimpleNamespace(offset=0, value={
                    "original_topic": "events",
                    "key": None,
                    "value": encode_dead_letter_field(b'{"n":1}'),
                })],
                second: [SimpleNamespace(offset=0, value={
                    "original_topic": "events",
                    "key": None,
                    "value": encode_dead_letter_field(b'{"n":2}'),
                })],
            }
            self.getone_partitions = []
            self.commits = []

        async def position(self, partition):
            return self.positions[partition]

        async def getone(self, partition):
            self.getone_partitions.append(partition)
            record = self.records[partition].pop(0)
            self.positions[partition] = record.offset + 1
            return record

        async def commit(self, offsets):
            self.commits.append(offsets)

    consumer = FakeConsumer()
    producer = AsyncMock()
    producer.send_raw.return_value = True

    assert await replay_partition(
        consumer=consumer, kafka_client=producer, partition=first, end_offset=1
    ) == (1, 0)
    assert await replay_partition(
        consumer=consumer, kafka_client=producer, partition=second, end_offset=1
    ) == (1, 0)
    assert consumer.getone_partitions == [first, second]
    assert [next(iter(commit)) for commit in consumer.commits] == [first, second]


@pytest.mark.asyncio
async def test_outbox_retention_is_bounded_by_batch_and_run_limit():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(OutboxMessageModel.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    old = datetime.now(timezone.utc) - timedelta(days=30)
    async with session_factory() as session:
        session.add_all(
            [
                OutboxMessageModel(
                    id=f"event-{index}",
                    aggregatetype="loan",
                    aggregateid=f"loan-{index}",
                    type="LoanCreated",
                    payload="{}",
                    occurred_at=old,
                    inserted_at=old,
                )
                for index in range(3)
            ]
        )
        await session.commit()

    deleted = await OutboxRetentionService(session_factory).prune(
        older_than=datetime.now(timezone.utc), batch_size=1, max_batches=2
    )
    assert deleted == 2
    async with session_factory() as session:
        remaining = list((await session.execute(select(OutboxMessageModel))).scalars())
        assert len(remaining) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_retention_uses_insertion_time_not_business_event_time():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(OutboxMessageModel.__table__.create)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    old_business_time = datetime.now(timezone.utc) - timedelta(days=30)
    inserted_at = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(
            OutboxMessageModel(
                id="delayed-historical-event",
                aggregatetype="loan",
                aggregateid="loan-delayed",
                type="library.lending.loan-created.v1",
                payload="{}",
                occurred_at=old_business_time,
                inserted_at=inserted_at,
            )
        )
        await session.commit()

    deleted = await OutboxRetentionService(session_factory).prune(
        older_than=inserted_at - timedelta(seconds=1)
    )

    assert deleted == 0
    async with session_factory() as session:
        remaining = await session.scalar(
            select(OutboxMessageModel).where(
                OutboxMessageModel.id == "delayed-historical-event"
            )
        )
        assert remaining is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_outbox_retention_rejects_ambiguous_naive_cutoff():
    service = OutboxRetentionService(AsyncMock())

    with pytest.raises(ValueError, match="timezone-aware"):
        await service.prune(older_than=datetime(2026, 7, 11))


@pytest.mark.asyncio
async def test_outbox_retention_rejects_invalid_replication_slot_identity():
    service = OutboxRetentionService(AsyncMock())

    with pytest.raises(ValueError, match="replication_slot"):
        await service.prune(
            older_than=datetime.now(timezone.utc),
            replication_slot="unsafe-slot;drop",
        )

"""
Unit tests for KafkaClient at-least-once consumption semantics.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka.errors import TopicAlreadyExistsError

from src.infrastructure.exceptions import (
    DurableMessageHandlingException,
    MessageBrokerException,
    UnrecoverableMessageException,
)
from src.infrastructure.external.kafka_client import (
    KafkaClient,
    decode_dead_letter_field,
)


class FakeConsumer:
    """Minimal stand-in for AIOKafkaConsumer."""

    def __init__(self, records):
        self._records = records
        self.commit = AsyncMock()

    def __aiter__(self):
        async def generator():
            for record in self._records:
                yield record
        return generator()


def _record(value=None):
    return SimpleNamespace(
        topic="library.public.books",
        partition=0,
        offset=42,
        key={"id": "book-1"},
        value=value or {"op": "c"},
    )


def _client(max_retries=2) -> KafkaClient:
    client = KafkaClient(
        consumer_max_retries=max_retries,
        retry_backoff_seconds=0.001,
        consumer_max_poll_interval_ms=100_000,
        message_processing_timeout_seconds=0.1,
        logger=MagicMock(),
    )
    # Topic creation talks to a real broker; stub it for unit tests
    client._ensure_topic = AsyncMock()
    return client


@pytest.mark.parametrize("timeout", [0, -1, 240.001, float("inf"), float("nan")])
def test_processing_timeout_must_fit_inside_handler_inbox_lease(timeout):
    with pytest.raises(ValueError, match="handler inbox lease"):
        KafkaClient(message_processing_timeout_seconds=timeout)


async def _drain(client, handler):
    async for _ in client.consume(handler=handler):
        pass


async def _drain_forever_policy(client, handler):
    async for _ in client.consume(handler=handler, retry_forever=True):
        pass


async def _drain_projection_policy(client, handler):
    async for _ in client.consume(
        handler=handler,
        retry_forever=True,
        park_unrecoverable=False,
    ):
        pass


@pytest.mark.asyncio
async def test_offset_commits_after_successful_handling():
    client = _client()
    client._consumer = FakeConsumer([_record()])
    handler = AsyncMock()

    await _drain(client, handler)

    handler.assert_awaited_once()
    client._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_raw_json_is_decoded_inside_the_handling_boundary():
    client = _client()
    client._consumer = FakeConsumer(
        [
            SimpleNamespace(
                topic="outbox.event.book",
                partition=1,
                offset=7,
                key=b'"book-1"',
                value=b'{"op":"c","after":{"id":"book-1"}}',
            )
        ]
    )
    handler = AsyncMock()

    await _drain(client, handler)

    handler.assert_awaited_once_with(
        "outbox.event.book",
        "book-1",
        {"op": "c", "after": {"id": "book-1"}},
    )
    client._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_malformed_json_is_losslessly_dead_lettered_then_committed():
    client = _client(max_retries=10)
    raw_key = b'"book-1"'
    raw_value = b'{"op":'
    client._consumer = FakeConsumer(
        [
            SimpleNamespace(
                topic="outbox.event.book",
                partition=1,
                offset=8,
                key=raw_key,
                value=raw_value,
            )
        ]
    )
    client.send = AsyncMock(return_value=True)
    handler = AsyncMock()

    await _drain_forever_policy(client, handler)

    handler.assert_not_awaited()
    client.send.assert_awaited_once()
    dlq_message = client.send.await_args.args[1]
    decoded_key, encoded_key = decode_dead_letter_field(dlq_message["key"])
    decoded_value, encoded_value = decode_dead_letter_field(dlq_message["value"])
    assert (decoded_key, encoded_key) == (raw_key, True)
    assert (decoded_value, encoded_value) == (raw_value, True)
    assert "Malformed Kafka value" in dlq_message["error"]
    client._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handler_is_retried_before_dead_lettering():
    client = _client(max_retries=2)
    client._consumer = FakeConsumer([_record()])
    client.send = AsyncMock(return_value=True)

    handler = AsyncMock(side_effect=[RuntimeError("transient"), None])
    await _drain(client, handler)

    assert handler.await_count == 2  # failed once, succeeded on retry
    client.send.assert_not_awaited()  # never dead-lettered
    client._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_durable_state_transition_exits_uncommitted_after_retry_budget():
    client = _client(max_retries=0)
    client._consumer = FakeConsumer([_record()])
    client.send = AsyncMock(return_value=True)
    handler = AsyncMock(side_effect=DurableMessageHandlingException("database down"))

    with pytest.raises(DurableMessageHandlingException):
        await _drain(client, handler)

    handler.assert_awaited_once()
    client.send.assert_not_awaited()
    client._consumer.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_forever_policy_is_bounded_per_poll_and_leaves_offset_uncommitted():
    client = _client(max_retries=1)
    client._consumer = FakeConsumer([_record()])
    client.send = AsyncMock(return_value=True)
    handler = AsyncMock(side_effect=RuntimeError("projection unavailable"))

    with pytest.raises(RuntimeError, match="projection unavailable"):
        await _drain_forever_policy(client, handler)

    assert handler.await_count == 2
    client.send.assert_not_awaited()
    client._consumer.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrecoverable_message_is_dead_lettered_under_durable_retry_policy():
    client = _client(max_retries=10)
    client._consumer = FakeConsumer([_record({"bad": "payload"})])
    client.send = AsyncMock(return_value=True)
    handler = AsyncMock(
        side_effect=UnrecoverableMessageException("invalid event schema")
    )

    await _drain_forever_policy(client, handler)

    handler.assert_awaited_once()
    client.send.assert_awaited_once()
    client._consumer.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_projection_poison_stays_uncommitted_so_lag_forces_fallback():
    client = _client(max_retries=10)
    client._consumer = FakeConsumer([_record({"bad": "payload"})])
    client.send = AsyncMock(return_value=True)
    handler = AsyncMock(
        side_effect=UnrecoverableMessageException("invalid CDC schema")
    )

    with pytest.raises(UnrecoverableMessageException):
        await _drain_projection_policy(client, handler)

    client.send.assert_not_awaited()
    client._consumer.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_poison_message_goes_to_dlq_then_commits():
    client = _client(max_retries=2)
    client._consumer = FakeConsumer([_record({"bad": "payload"})])
    client.send = AsyncMock(return_value=True)

    handler = AsyncMock(side_effect=RuntimeError("poison"))
    await _drain(client, handler)

    assert handler.await_count == 3  # initial + 2 retries
    client.send.assert_awaited_once()
    dlq_topic = client.send.await_args.args[0]
    dlq_message = client.send.await_args.args[1]
    assert dlq_topic == "library.public.books.dlq"
    assert dlq_message["original_topic"] == "library.public.books"
    assert dlq_message["offset"] == 42
    assert "poison" in dlq_message["error"]
    client._consumer.commit.assert_awaited_once()  # parked, then committed


@pytest.mark.asyncio
async def test_dlq_topic_is_created_before_first_use():
    """The broker runs without auto-create; the DLQ owner creates its topic."""
    client = _client(max_retries=0)
    client._consumer = FakeConsumer([_record()])
    client.send = AsyncMock(return_value=True)

    handler = AsyncMock(side_effect=RuntimeError("poison"))
    await _drain(client, handler)

    client._ensure_topic.assert_awaited_once_with("library.public.books.dlq")


@pytest.mark.asyncio
async def test_ensure_topic_is_cached_after_success():
    client = KafkaClient(logger=MagicMock())
    client._ensured_topics.add("already.done.dlq")

    # Cached topics never touch the admin client (would raise on connect)
    await client._ensure_topic("already.done.dlq")


@pytest.mark.asyncio
async def test_producer_enables_idempotence_for_dlq_durability():
    producer = MagicMock()
    producer.start = AsyncMock()
    client = _client()

    with patch(
        "src.infrastructure.external.kafka_client.AIOKafkaProducer",
        return_value=producer,
    ) as producer_type:
        await client.connect_producer()

    assert producer_type.call_args.kwargs["enable_idempotence"] is True


@pytest.mark.asyncio
async def test_dlq_topic_uses_configured_replication_factor():
    admin = MagicMock()
    admin.start = AsyncMock()
    admin.close = AsyncMock()
    admin.create_topics = AsyncMock()
    admin.describe_topics = AsyncMock(
        return_value=[
            {
                "topic": "events.dlq",
                "partitions": [{"replicas": list(range(5))}],
            }
        ]
    )
    client = KafkaClient(
        internal_topic_replication_factor=5,
        logger=MagicMock(),
    )

    with patch(
        "src.infrastructure.external.kafka_client.AIOKafkaAdminClient",
        return_value=admin,
    ):
        await client._ensure_topic("events.dlq")

    topic = admin.create_topics.await_args.args[0][0]
    assert topic.replication_factor == 5


@pytest.mark.asyncio
async def test_existing_under_replicated_dlq_topic_is_rejected():
    admin = MagicMock()
    admin.start = AsyncMock()
    admin.close = AsyncMock()
    admin.create_topics = AsyncMock(side_effect=TopicAlreadyExistsError())
    admin.describe_topics = AsyncMock(
        return_value=[
            {"topic": "events.dlq", "partitions": [{"replicas": [0]}]}
        ]
    )
    client = KafkaClient(
        internal_topic_replication_factor=3,
        logger=MagicMock(),
    )

    with patch(
        "src.infrastructure.external.kafka_client.AIOKafkaAdminClient",
        return_value=admin,
    ):
        with pytest.raises(MessageBrokerException, match="replication_factor>=3"):
            await client._ensure_topic("events.dlq")

    assert "events.dlq" not in client._ensured_topics
    admin.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_dlq_publish_raises_without_committing():
    client = _client(max_retries=1)
    client._consumer = FakeConsumer([_record()])
    client.send = AsyncMock(return_value=False)  # DLQ publish fails

    handler = AsyncMock(side_effect=RuntimeError("poison"))
    with pytest.raises(MessageBrokerException):
        await _drain(client, handler)

    # Not committed: the message redelivers on restart instead of being lost
    client._consumer.commit.assert_not_awaited()

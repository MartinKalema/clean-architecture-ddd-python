"""
Unit tests for KafkaClient at-least-once consumption semantics.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.exceptions import MessageBrokerException
from src.infrastructure.external.kafka_client import KafkaClient


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
        logger=MagicMock(),
    )
    # Topic creation talks to a real broker; stub it for unit tests
    client._ensure_topic = AsyncMock()
    return client


async def _drain(client, handler):
    async for _ in client.consume(handler=handler):
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
async def test_failed_dlq_publish_raises_without_committing():
    client = _client(max_retries=1)
    client._consumer = FakeConsumer([_record()])
    client.send = AsyncMock(return_value=False)  # DLQ publish fails

    handler = AsyncMock(side_effect=RuntimeError("poison"))
    with pytest.raises(MessageBrokerException):
        await _drain(client, handler)

    # Not committed: the message redelivers on restart instead of being lost
    client._consumer.commit.assert_not_awaited()

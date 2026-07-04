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
    return KafkaClient(
        consumer_max_retries=max_retries,
        retry_backoff_seconds=0.001,
        logger=MagicMock(),
    )


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
async def test_failed_dlq_publish_raises_without_committing():
    client = _client(max_retries=1)
    client._consumer = FakeConsumer([_record()])
    client.send = AsyncMock(return_value=False)  # DLQ publish fails

    handler = AsyncMock(side_effect=RuntimeError("poison"))
    with pytest.raises(MessageBrokerException):
        await _drain(client, handler)

    # Not committed: the message redelivers on restart instead of being lost
    client._consumer.commit.assert_not_awaited()

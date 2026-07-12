from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka.structs import OffsetAndMetadata, TopicPartition

from src.infrastructure.adapters.cdc.kafka_projection_freshness import (
    KafkaProjectionFreshness,
)


def _gate():
    gate = KafkaProjectionFreshness(
        bootstrap_servers="kafka:9092",
        group_id="projection-v1",
        topics=["books", "loans"],
        logger=MagicMock(),
        cache_seconds=0,
    )
    gate._admin = AsyncMock()
    gate._consumer = AsyncMock()
    gate._consumer.partitions_for_topic = MagicMock()
    return gate


@pytest.mark.asyncio
async def test_projection_is_fresh_only_when_every_nonempty_partition_is_committed():
    gate = _gate()
    book = TopicPartition("books", 0)
    loan = TopicPartition("loans", 0)
    gate._consumer.partitions_for_topic.side_effect = [{0}, {0}]
    gate._consumer.end_offsets.return_value = {book: 4, loan: 0}
    gate._admin.list_consumer_group_offsets.return_value = {
        book: OffsetAndMetadata(4, "")
    }

    assert await gate.is_fresh() is True


@pytest.mark.asyncio
async def test_projection_lag_or_kafka_failure_forces_postgresql_fallback():
    gate = _gate()
    book = TopicPartition("books", 0)
    loan = TopicPartition("loans", 0)
    gate._consumer.partitions_for_topic.side_effect = [{0}, {0}]
    gate._consumer.end_offsets.return_value = {book: 5, loan: 0}
    gate._admin.list_consumer_group_offsets.return_value = {
        book: OffsetAndMetadata(4, "")
    }

    assert await gate.is_fresh() is False

    gate._consumer.partitions_for_topic.side_effect = RuntimeError("broker down")
    assert await gate.is_fresh() is False

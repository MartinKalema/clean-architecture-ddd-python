#!/usr/bin/env python
"""
Dead-Letter Queue Replay

Re-publishes messages parked on a dead-letter topic back onto their
original topic, where the normal consumers process them again. Use after
fixing the defect that caused the dead-lettering; handlers are idempotent,
so replaying already-applied work is safe.

Each DLQ message is the wrapper written by KafkaClient._send_to_dead_letter:
{original_topic, partition, offset, key, value, error}.

Usage:
    python scripts/replay_dlq.py --topic outbox.event.loan.dlq

Environment variables:
    ETCD_HOST: etcd host (default: localhost)
    ETCD_PORT: etcd port (default: 2379)
"""
import argparse
import asyncio
import json
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from aiokafka import AIOKafkaConsumer
from aiokafka.structs import OffsetAndMetadata, TopicPartition

from src.container import Container
from src.infrastructure.external.kafka_client import decode_dead_letter_field


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a dead-letter topic")
    parser.add_argument("--topic", required=True, help="DLQ topic to replay (e.g. outbox.event.loan.dlq)")
    parser.add_argument(
        "--from-beginning",
        action="store_true",
        help="Ignore this replay consumer group's committed offsets",
    )
    args = parser.parse_args()

    container = Container()

    # Load configuration from etcd
    etcd_adapter = container.etcd_adapter()
    etcd_adapter.load()
    container.configurations.from_dict(etcd_adapter.get_all())

    logger = container.logger()
    kafka_client = container.kafka_client()
    bootstrap = container.configurations.kafka.bootstrap_servers()

    consumer = AIOKafkaConsumer(
        bootstrap_servers=bootstrap,
        group_id=f"dlq-replay-{args.topic}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
    )
    await consumer.start()

    try:
        partition_ids = await consumer.partitions_for_topic(args.topic)
        if not partition_ids:
            logger.info(f"No partitions assigned for {args.topic}; nothing to replay")
            return
        partitions = [
            TopicPartition(args.topic, partition_id)
            for partition_id in sorted(partition_ids)
        ]
        consumer.assign(partitions)

        beginning_offsets = await consumer.beginning_offsets(partitions)
        end_offsets = await consumer.end_offsets(partitions)

        replayed = 0
        skipped = 0
        for tp in partitions:
            committed = None if args.from_beginning else await consumer.committed(tp)
            start_offset = (
                committed
                if committed is not None
                else beginning_offsets[tp]
            )
            consumer.seek(tp, start_offset)
            partition_replayed, partition_skipped = await replay_partition(
                consumer=consumer,
                kafka_client=kafka_client,
                partition=tp,
                end_offset=end_offsets[tp],
            )
            replayed += partition_replayed
            skipped += partition_skipped

        logger.info(f"Replayed {replayed} message(s) from {args.topic} ({skipped} skipped)")

    finally:
        await consumer.stop()
        await kafka_client.close()


async def replay_partition(
    *,
    consumer: AIOKafkaConsumer,
    kafka_client,
    partition: TopicPartition,
    end_offset: int,
) -> tuple[int, int]:
    """Replay exactly one partition and commit only its confirmed progress."""
    replayed = 0
    skipped = 0
    while await consumer.position(partition) < end_offset:
        record = await consumer.getone(partition)
        wrapper = record.value
        if not isinstance(wrapper, dict) or not isinstance(
            wrapper.get("original_topic"), str
        ) or "value" not in wrapper:
            skipped += 1
        else:
            replay_value, value_is_raw = decode_dead_letter_field(
                wrapper["value"]
            )
            replay_key, key_is_raw = decode_dead_letter_field(
                wrapper.get("key")
            )
            if value_is_raw or key_is_raw:
                delivered = await kafka_client.send_raw(
                    wrapper["original_topic"],
                    value=_as_kafka_bytes(replay_value, value_is_raw),
                    key=_as_kafka_bytes(replay_key, key_is_raw),
                )
            else:
                # Backward compatibility with DLQ envelopes written before
                # KafkaClient began preserving original wire bytes.
                delivered = await kafka_client.send(
                    wrapper["original_topic"],
                    value=replay_value,
                    key=replay_key,
                )
            if not delivered:
                raise RuntimeError(
                    f"Failed to re-publish {partition.topic}[{partition.partition}] "
                    f"offset {record.offset}; its DLQ offset was not committed"
                )
            replayed += 1

        await consumer.commit(
            {partition: OffsetAndMetadata(record.offset + 1, "")}
        )
    return replayed, skipped


def _as_kafka_bytes(value, already_raw: bool) -> bytes | None:
    if value is None:
        return None
    if already_raw:
        if not isinstance(value, bytes):
            raise TypeError("decoded DLQ binary field is not bytes")
        return value
    return json.dumps(value).encode("utf-8")


if __name__ == "__main__":
    asyncio.run(main())

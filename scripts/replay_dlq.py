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
import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from aiokafka import AIOKafkaConsumer

from src.container import Container


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a dead-letter topic")
    parser.add_argument("--topic", required=True, help="DLQ topic to replay (e.g. outbox.event.loan.dlq)")
    args = parser.parse_args()

    container = Container()

    # Load configuration from etcd
    etcd_adapter = container.etcd_adapter()
    etcd_adapter.load()
    container.configurations.from_dict(etcd_adapter.get_all())

    logger = container.logger()
    kafka_client = container.kafka_client()
    bootstrap = container.configurations.kafka.bootstrap_servers()

    import json
    consumer = AIOKafkaConsumer(
        args.topic,
        bootstrap_servers=bootstrap,
        group_id=f"dlq-replay-{args.topic}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
    )
    await consumer.start()

    try:
        # Partition metadata only populates for subscribed topics; wait for
        # the group assignment instead of reading the cache directly
        for _ in range(100):
            if consumer.assignment():
                break
            await asyncio.sleep(0.1)

        partitions = list(consumer.assignment())
        if not partitions:
            logger.info(f"No partitions assigned for {args.topic}; nothing to replay")
            return

        end_offsets = await consumer.end_offsets(partitions)

        replayed = 0
        skipped = 0
        for tp in partitions:
            position = await consumer.position(tp)
            while position < end_offsets[tp]:
                record = await consumer.getone()
                position = record.offset + 1

                wrapper = record.value
                if not wrapper or "original_topic" not in wrapper:
                    skipped += 1
                    continue

                delivered = await kafka_client.send(
                    wrapper["original_topic"],
                    value=wrapper["value"],
                    key=wrapper.get("key"),
                )
                if not delivered:
                    raise RuntimeError(
                        f"Failed to re-publish offset {record.offset}; aborting "
                        f"(nothing is lost — the DLQ retains all messages)"
                    )
                replayed += 1

        await consumer.commit()
        logger.info(f"Replayed {replayed} message(s) from {args.topic} ({skipped} skipped)")

    finally:
        await consumer.stop()
        await kafka_client.close()


if __name__ == "__main__":
    asyncio.run(main())

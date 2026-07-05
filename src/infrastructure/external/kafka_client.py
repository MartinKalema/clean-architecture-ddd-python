"""
Kafka Client - External service wrapper for Apache Kafka.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from src.infrastructure.exceptions import MessageBrokerException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger

# How often the consume loop logs consumer lag (staleness of the pipeline).
LAG_LOG_INTERVAL_SECONDS = 60.0


class KafkaClient:
    """
    Async client for Kafka messaging operations.

    Provides producer and consumer functionality with JSON serialization.
    Configuration is loaded from etcd via dependency injection.

    Consumption is at-least-once: offsets are committed only after a message
    has been handled successfully (or parked on a dead-letter topic after
    exhausting retries). Handlers must therefore be idempotent.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        consumer_max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        logger: Optional[ILogger] = None,
    ):
        self._bootstrap_servers = bootstrap_servers
        self._consumer_max_retries = consumer_max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._logger = logger
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._ensured_topics: set[str] = set()

    async def connect_producer(self) -> None:
        """Establish producer connection to Kafka."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: json.dumps(k).encode("utf-8") if k else None,
            )
            await self._producer.start()
            if self._logger:
                self._logger.info(f"Kafka producer connected to {self._bootstrap_servers}")

    async def connect_consumer(
        self,
        topics: list[str],
        group_id: str,
        auto_offset_reset: str = "earliest",
    ) -> None:
        """
        Establish consumer connection to Kafka.

        Auto-commit is disabled: offsets are committed by consume() only
        after a message has been fully handled, so a crash mid-message
        redelivers it instead of silently dropping it.
        """
        if self._consumer is None:
            self._consumer = AIOKafkaConsumer(
                *topics,
                bootstrap_servers=self._bootstrap_servers,
                group_id=group_id,
                auto_offset_reset=auto_offset_reset,
                enable_auto_commit=False,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
                key_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
            )
            await self._consumer.start()
            if self._logger:
                self._logger.info(f"Kafka consumer connected to {self._bootstrap_servers}, topics: {topics}")

    async def close(self) -> None:
        """Close all Kafka connections."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            if self._logger:
                self._logger.info("Kafka producer disconnected")

        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
            if self._logger:
                self._logger.info("Kafka consumer disconnected")

    async def send(
        self,
        topic: str,
        value: dict[str, Any],
        key: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Send a message to a Kafka topic."""
        if not self._producer:
            await self.connect_producer()

        try:
            await self._producer.send_and_wait(topic, value=value, key=key)
            return True
        except Exception as e:
            if self._logger:
                self._logger.error(f"Kafka send error: {e}")
            return False

    async def consume(
        self,
        handler: Callable[[str, dict | None, dict | None], Any],
    ) -> AsyncIterator[None]:
        """
        Consume messages with at-least-once semantics and yield after each.

        Each message is retried with exponential backoff; a message that
        still fails is published to <topic>.dlq before its offset commits,
        so it is parked for inspection instead of lost or blocking the
        partition. If the dead-letter publish itself fails, the consumer
        raises without committing and the message is redelivered on restart.

        Args:
            handler: Async callback function(topic, key, value) for each message
        """
        if not self._consumer:
            raise RuntimeError("Consumer not connected. Call connect_consumer first.")

        last_lag_log = time.monotonic()

        async for record in self._consumer:
            await self._handle_with_retry(record, handler)
            await self._consumer.commit()

            if time.monotonic() - last_lag_log >= LAG_LOG_INTERVAL_SECONDS:
                await self._log_consumer_lag()
                last_lag_log = time.monotonic()

            yield

    async def _handle_with_retry(self, record, handler) -> None:
        """Invoke the handler, retrying with backoff; dead-letter on exhaustion."""
        for attempt in range(self._consumer_max_retries + 1):
            try:
                await handler(record.topic, record.key, record.value)
                return
            except Exception as e:
                if attempt < self._consumer_max_retries:
                    backoff = self._retry_backoff_seconds * (2 ** attempt)
                    if self._logger:
                        self._logger.warning(
                            f"Error processing message from {record.topic} "
                            f"(offset {record.offset}), attempt "
                            f"{attempt + 1}/{self._consumer_max_retries}: {e}. "
                            f"Retrying in {backoff:.1f}s"
                        )
                    await asyncio.sleep(backoff)
                else:
                    await self._send_to_dead_letter(record, e)

    async def _ensure_topic(self, topic: str, partitions: int = 1) -> None:
        """
        Create an app-owned internal topic (DLQ) if it does not exist.

        The broker runs with auto-create disabled (production posture), so
        the component that owns a topic creates it: Debezium declares its
        data topics via topic.creation.*, and the messaging layer creates
        its dead-letter topics here on first use.
        """
        if topic in self._ensured_topics:
            return

        admin = AIOKafkaAdminClient(bootstrap_servers=self._bootstrap_servers)
        await admin.start()
        try:
            await admin.create_topics(
                [NewTopic(name=topic, num_partitions=partitions, replication_factor=1)]
            )
            if self._logger:
                self._logger.info(f"Created topic {topic}")
        except TopicAlreadyExistsError:
            pass
        finally:
            await admin.close()

        self._ensured_topics.add(topic)

    async def _send_to_dead_letter(self, record, error: Exception) -> None:
        """Park an unprocessable message on the topic's dead-letter queue."""
        dlq_topic = f"{record.topic}.dlq"
        await self._ensure_topic(dlq_topic)
        message = {
            "original_topic": record.topic,
            "partition": record.partition,
            "offset": record.offset,
            "key": record.key,
            "value": record.value,
            "error": str(error),
        }

        if self._logger:
            self._logger.error(
                f"Message from {record.topic} (offset {record.offset}) failed "
                f"after {self._consumer_max_retries} retries; "
                f"sending to {dlq_topic}: {error}"
            )

        delivered = await self.send(dlq_topic, message, key=record.key)
        if not delivered:
            # Better to crash without committing (message redelivers on
            # restart) than to commit and lose it.
            raise MessageBrokerException(
                f"Failed to dead-letter message from {record.topic} "
                f"(offset {record.offset})",
                original_exception=error,
            )

    async def _log_consumer_lag(self) -> None:
        """Log per-partition consumer lag — the pipeline's staleness metric."""
        if not self._consumer or not self._logger:
            return

        try:
            lag = await self.get_consumer_lag()
            total = sum(lag.values())
            self._logger.info(f"Consumer lag: total={total}, partitions={lag}")
        except Exception as e:
            self._logger.warning(f"Could not compute consumer lag: {e}")

    async def get_consumer_lag(self) -> dict[str, int]:
        """Return lag (highwater - position) per assigned partition."""
        if not self._consumer:
            return {}

        lag: dict[str, int] = {}
        for tp in self._consumer.assignment():
            highwater = self._consumer.highwater(tp)
            if highwater is None:
                continue
            position = await self._consumer.position(tp)
            lag[f"{tp.topic}[{tp.partition}]"] = max(0, highwater - position)
        return lag

    @property
    def is_producer_connected(self) -> bool:
        """Check if producer is connected."""
        return self._producer is not None

    @property
    def is_consumer_connected(self) -> bool:
        """Check if consumer is connected."""
        return self._consumer is not None

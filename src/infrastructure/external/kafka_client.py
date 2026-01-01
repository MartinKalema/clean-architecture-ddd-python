"""
Kafka Client - External service wrapper for Apache Kafka.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable, Iterator, Optional

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class KafkaClient:
    """
    Client for Kafka messaging operations.

    Provides producer and consumer functionality with JSON serialization.
    Configuration is loaded from etcd via dependency injection.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        logger: Optional[ILogger] = None,
    ):
        self._bootstrap_servers = bootstrap_servers
        self._logger = logger
        self._producer: Optional[KafkaProducer] = None
        self._consumer: Optional[KafkaConsumer] = None

    def connect_producer(self) -> None:
        """Establish producer connection to Kafka."""
        if self._producer is None:
            self._producer = KafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                key_serializer=lambda k: json.dumps(k).encode("utf-8") if k else None,
            )
            if self._logger:
                self._logger.info(f"Kafka producer connected to {self._bootstrap_servers}")

    def connect_consumer(
        self,
        topics: list[str],
        group_id: str,
        auto_offset_reset: str = "earliest",
    ) -> None:
        """Establish consumer connection to Kafka."""
        if self._consumer is None:
            self._consumer = KafkaConsumer(
                *topics,
                bootstrap_servers=self._bootstrap_servers,
                group_id=group_id,
                auto_offset_reset=auto_offset_reset,
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
                key_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
            )
            if self._logger:
                self._logger.info(f"Kafka consumer connected to {self._bootstrap_servers}, topics: {topics}")

    def close(self) -> None:
        """Close all Kafka connections."""
        if self._producer:
            self._producer.close()
            self._producer = None
            if self._logger:
                self._logger.info("Kafka producer disconnected")

        if self._consumer:
            self._consumer.close()
            self._consumer = None
            if self._logger:
                self._logger.info("Kafka consumer disconnected")

    def send(
        self,
        topic: str,
        value: dict[str, Any],
        key: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Send a message to a Kafka topic."""
        if not self._producer:
            self.connect_producer()

        try:
            future = self._producer.send(topic, value=value, key=key)
            future.get(timeout=10)
            return True
        except KafkaError as e:
            if self._logger:
                self._logger.error(f"Kafka send error: {e}")
            return False

    def poll(self, timeout_ms: int = 1000) -> dict[str, list[dict[str, Any]]]:
        """Poll for messages from subscribed topics."""
        if not self._consumer:
            raise RuntimeError("Consumer not connected. Call connect_consumer first.")

        messages = self._consumer.poll(timeout_ms=timeout_ms)
        result: dict[str, list[dict[str, Any]]] = {}

        for topic_partition, records in messages.items():
            topic = topic_partition.topic
            if topic not in result:
                result[topic] = []

            for record in records:
                result[topic].append({
                    "key": record.key,
                    "value": record.value,
                    "topic": record.topic,
                    "partition": record.partition,
                    "offset": record.offset,
                    "timestamp": record.timestamp,
                })

        return result

    def consume(
        self,
        handler: Callable[[str, dict | None, dict | None], None],
        poll_timeout_ms: int = 1000,
    ) -> Iterator[None]:
        """
        Consume messages and yield after each batch.

        Args:
            handler: Callback function(topic, key, value) for each message
            poll_timeout_ms: Timeout for each poll cycle
        """
        if not self._consumer:
            raise RuntimeError("Consumer not connected. Call connect_consumer first.")

        while True:
            messages = self._consumer.poll(timeout_ms=poll_timeout_ms)

            for topic_partition, records in messages.items():
                for record in records:
                    try:
                        handler(record.topic, record.key, record.value)
                    except Exception as e:
                        if self._logger:
                            self._logger.error(f"Error processing message: {e}")

            yield

    @property
    def is_producer_connected(self) -> bool:
        """Check if producer is connected."""
        return self._producer is not None

    @property
    def is_consumer_connected(self) -> bool:
        """Check if consumer is connected."""
        return self._consumer is not None

"""
Kafka Client - External service wrapper for Apache Kafka.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class KafkaClient:
    """
    Async client for Kafka messaging operations.

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
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumer: Optional[AIOKafkaConsumer] = None

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
        """Establish consumer connection to Kafka."""
        if self._consumer is None:
            self._consumer = AIOKafkaConsumer(
                *topics,
                bootstrap_servers=self._bootstrap_servers,
                group_id=group_id,
                auto_offset_reset=auto_offset_reset,
                enable_auto_commit=True,
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
        Consume messages and yield after each message.

        Args:
            handler: Async callback function(topic, key, value) for each message
        """
        if not self._consumer:
            raise RuntimeError("Consumer not connected. Call connect_consumer first.")

        async for record in self._consumer:
            try:
                await handler(record.topic, record.key, record.value)
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

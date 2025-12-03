from typing import Optional

from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]
from aiokafka.errors import KafkaError  # type: ignore[import-untyped]

from src.domain.shared_kernel import Logger


class KafkaClient:
    def __init__(self, bootstrap_servers: str, logger: Logger):
        self.bootstrap_servers = bootstrap_servers
        self.logger = logger
        self.producer: Optional[AIOKafkaProducer] = None

    async def connect(self) -> None:
        if not self.producer:
            try:
                self.producer = AIOKafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    value_serializer=lambda v: v,
                    acks='all',
                    enable_idempotence=True,
                )
                await self.producer.start()
                self.logger.info(f"Connected to Kafka: {self.bootstrap_servers}")
            except KafkaError as e:
                self.logger.error(f"Failed to connect to Kafka: {e}", exception=e)
                raise

    async def close(self) -> None:
        if self.producer:
            await self.producer.stop()
            self.producer = None
            self.logger.info("Kafka producer closed")

    async def publish(self, topic: str, key: Optional[str], message_body: bytes) -> None:
        if not self.producer:
            self.logger.error("Attempted to publish without initialized producer")
            raise ConnectionError("Kafka producer not initialized. Call connect() first.")

        key_bytes = key.encode() if key else None
        await self.producer.send_and_wait(topic, value=message_body, key=key_bytes)
        self.logger.debug(f"Published message to topic {topic}")

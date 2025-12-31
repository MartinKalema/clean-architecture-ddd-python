from __future__ import annotations

from typing import TYPE_CHECKING

import aio_pika

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class RabbitMQClient:
    def __init__(self, amqp_url: str, logger: ILogger):
        self.amqp_url = amqp_url
        self.logger = logger
        self.connection = None
        self.channel = None
        self.exchange = None

    async def connect(self, exchange_name: str):
        if not self.connection:
            try:
                connection = await aio_pika.connect_robust(self.amqp_url)
                self.connection = connection
                channel = await connection.channel()
                self.channel = channel
                self.exchange = await channel.declare_exchange(
                    exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
                )
                self.logger.info(f"Connected to RabbitMQ exchange: {exchange_name}")
            except Exception as e:
                self.logger.error(f"Failed to connect to RabbitMQ: {e}", exception=e)
                raise e

    async def close(self):
        if self.connection:
            await self.connection.close()
            self.logger.info("RabbitMQ connection closed")

    async def publish(self, routing_key: str, message_body: bytes):
        if not self.exchange:
            self.logger.error("Attempted to publish without initialized exchange")
            raise ConnectionError("RabbitMQ exchange not initialized. Call connect() first.")

        message = aio_pika.Message(
            body=message_body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.exchange.publish(message, routing_key=routing_key)
        self.logger.debug(f"Published message to {routing_key}")

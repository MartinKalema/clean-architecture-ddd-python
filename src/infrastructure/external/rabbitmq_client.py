import aio_pika
import json

class RabbitMQClient:
    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url
        self.connection = None
        self.channel = None
        self.exchange = None

    async def connect(self, exchange_name: str):
        if not self.connection:
            self.connection = await aio_pika.connect_robust(self.amqp_url)
            self.channel = await self.connection.channel()
            self.exchange = await self.channel.declare_exchange(
                exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
            )

    async def close(self):
        if self.connection:
            await self.connection.close()

    async def publish(self, routing_key: str, message_body: bytes):
        if not self.exchange:
            raise ConnectionError("RabbitMQ exchange not initialized. Call connect() first.")

        message = aio_pika.Message(
            body=message_body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )

        await self.exchange.publish(message, routing_key=routing_key)

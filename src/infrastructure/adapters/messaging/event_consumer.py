"""
RabbitMQ Event Consumer

Consumes domain events from RabbitMQ and dispatches them to handlers.
This runs as a separate worker process.
"""
import json
from typing import Awaitable, Callable, Dict

import aio_pika
from aio_pika import IncomingMessage

from src.domain.shared_kernel import Logger


class EventConsumer:
    """
    Consumes events from RabbitMQ and dispatches to registered handlers.

    Usage:
        consumer = EventConsumer(amqp_url, exchange_name, queue_name, logger)
        consumer.register_handler("BookBorrowed", book_handlers.handle_book_borrowed)
        await consumer.start()
    """

    def __init__(
        self,
        amqp_url: str,
        exchange_name: str,
        queue_name: str,
        logger: Logger
    ):
        self.amqp_url = amqp_url
        self.exchange_name = exchange_name
        self.queue_name = queue_name
        self.logger = logger
        self.handlers: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._connection = None
        self._channel = None
        self._running = False

    def register_handler(
        self,
        event_type: str,
        handler: Callable[[dict], Awaitable[None]]
    ) -> None:
        """Register a handler for a specific event type."""
        self.handlers[event_type] = handler
        self.logger.info(f"Registered handler for event: {event_type}")

    async def start(self) -> None:
        """Start consuming events from RabbitMQ."""
        self._running = True

        try:
            connection = await aio_pika.connect_robust(self.amqp_url)
            self._connection = connection
            channel = await connection.channel()
            self._channel = channel

            await channel.set_qos(prefetch_count=10)

            exchange = await channel.declare_exchange(
                self.exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            queue = await channel.declare_queue(
                self.queue_name,
                durable=True
            )

            for event_type in self.handlers.keys():
                await queue.bind(exchange, routing_key=event_type)
                self.logger.info(f"Bound queue to routing key: {event_type}")

            self.logger.info(f"Event consumer started, listening on queue: {self.queue_name}")

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self._running:
                        break
                    await self._process_message(message)

        except Exception as e:
            self.logger.error("Event consumer error", exception=e)
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        self._running = False
        if self._connection:
            await self._connection.close()
        self.logger.info("Event consumer stopped")

    async def _process_message(self, message: IncomingMessage) -> None:
        """Process a single message from the queue."""
        async with message.process():
            try:
                body = json.loads(message.body.decode())
                event_type = body.get("event_name")
                payload = body.get("payload", {})

                handler = self.handlers.get(event_type)
                if handler:
                    self.logger.info(f"Processing event: {event_type}")
                    await handler(payload)
                    self.logger.info(f"Successfully processed event: {event_type}")
                else:
                    self.logger.warning(f"No handler registered for event: {event_type}")

            except json.JSONDecodeError as e:
                self.logger.error("Failed to decode message", exception=e)
            except Exception as e:
                self.logger.error("Error processing message", exception=e)
                raise

"""
Kafka Event Consumer

Consumes domain events from Kafka topics and dispatches them to handlers.
Supports consumer groups for scalable event processing.
"""
import json
from typing import Awaitable, Callable, Dict, List, Optional

from aiokafka import AIOKafkaConsumer  # type: ignore[import-untyped]
from aiokafka.errors import KafkaError  # type: ignore[import-untyped]

from src.domain.shared_kernel import Logger


class KafkaEventConsumer:
    """
    Consumes events from Kafka and dispatches to registered handlers.

    Features:
    - Consumer group support for horizontal scaling
    - Automatic offset management
    - Graceful shutdown
    - Dead letter handling (optional)

    Usage:
        consumer = KafkaEventConsumer(
            bootstrap_servers="localhost:9092",
            group_id="library-service",
            topic_prefix="domain_events",
            logger=logger
        )
        consumer.register_handler("BookBorrowed", handle_book_borrowed)
        await consumer.start()
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topic_prefix: str,
        logger: Logger,
        auto_offset_reset: str = "earliest"
    ):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topic_prefix = topic_prefix
        self.logger = logger
        self.auto_offset_reset = auto_offset_reset
        self.handlers: Dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False

    def register_handler(
        self,
        event_type: str,
        handler: Callable[[dict], Awaitable[None]]
    ) -> None:
        """Register a handler for a specific event type."""
        self.handlers[event_type] = handler
        self.logger.info(f"Registered handler for event: {event_type}")

    def _get_topics(self) -> List[str]:
        """Generate topic names from registered handlers."""
        topics = []
        for event_type in self.handlers.keys():
            if self.topic_prefix:
                topics.append(f"{self.topic_prefix}.{event_type}")
            else:
                topics.append(event_type)
        return topics

    async def start(self) -> None:
        """Start consuming events from Kafka."""
        self._running = True
        topics = self._get_topics()

        if not topics:
            self.logger.warning("No handlers registered, nothing to consume")
            return

        try:
            self._consumer = AIOKafkaConsumer(
                *topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                enable_auto_commit=True,
                value_deserializer=lambda m: m.decode('utf-8')
            )

            await self._consumer.start()
            self.logger.info(
                f"Kafka consumer started, group={self.group_id}, topics={topics}"
            )

            async for message in self._consumer:
                if not self._running:
                    break
                await self._process_message(message)

        except KafkaError as e:
            self.logger.error("Kafka consumer error", exception=e)
            raise
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
        self.logger.info("Kafka consumer stopped")

    async def _process_message(self, message) -> None:
        """Process a single message from Kafka."""
        try:
            body = json.loads(message.value)
            event_type = body.get("event_name")
            payload = body.get("payload", {})

            handler = self.handlers.get(event_type)
            if handler:
                self.logger.info(
                    f"Processing event: {event_type} from topic: {message.topic} "
                    f"partition: {message.partition} offset: {message.offset}"
                )
                await handler(payload)
                self.logger.info(f"Successfully processed event: {event_type}")
            else:
                self.logger.warning(f"No handler registered for event: {event_type}")

        except json.JSONDecodeError as e:
            self.logger.error("Failed to decode message", exception=e)
        except Exception as e:
            self.logger.error("Error processing message", exception=e)
            raise

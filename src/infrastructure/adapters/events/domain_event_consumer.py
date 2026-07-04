"""
Domain Event Consumer

Consumes domain events from the outbox Kafka topics (published by the
Debezium Outbox Event Router) and dispatches them to application-layer
event handlers.

Flow:
    UoW commit -> outbox table -> Debezium (WAL) -> Kafka
        -> this consumer -> EventDispatcher -> application event handlers

Delivery is at-least-once: Kafka may redeliver a message after a consumer
restart, so all subscribed handlers must be idempotent.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.infrastructure.adapters.events.event_registry import deserialize_event

if TYPE_CHECKING:
    from src.domain.shared_kernel import IEventDispatcher, ILogger
    from src.infrastructure.external.kafka_client import KafkaClient

# One topic per aggregate type, as routed by the Debezium Outbox Event Router
# (outbox.event.<aggregatetype>).
OUTBOX_TOPICS = [
    "outbox.event.book",
    "outbox.event.patron",
    "outbox.event.loan",
]


class DomainEventConsumer:
    """Consumes outbox events from Kafka and dispatches them to handlers."""

    def __init__(
        self,
        kafka_client: KafkaClient,
        event_dispatcher: IEventDispatcher,
        logger: ILogger,
        topics: Optional[list[str]] = None,
    ) -> None:
        self._kafka = kafka_client
        self._dispatcher = event_dispatcher
        self._logger = logger
        self._topics = topics or OUTBOX_TOPICS
        self._running = False

    async def _process_message(
        self, topic: str, _key: dict | str | None, value: dict | None
    ) -> None:
        """Deserialize one outbox message and dispatch the domain event."""
        if value is None:
            return

        event = deserialize_event(value)
        if event is None:
            self._logger.warning(
                f"Unknown event type on {topic}: {value.get('event_type')!r}"
            )
            return

        self._logger.info(
            f"Dispatching {event.event_type} (event_id={event.event_id})"
        )
        await self._dispatcher.dispatch(event)

    async def start(self) -> None:
        """Start the consumer loop."""
        self._logger.info(f"Connecting to Kafka, topics: {self._topics}")

        await self._kafka.connect_consumer(
            topics=self._topics,
            group_id="domain-event-worker",
        )

        self._running = True
        self._logger.info("Starting domain event consumer loop...")

        try:
            async for _ in self._kafka.consume(handler=self._process_message):
                if not self._running:
                    break
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        await self._kafka.close()
        self._logger.info("Domain event consumer stopped")

"""
Kafka Event Dispatcher with Circuit Breaker protection.

Publishes domain events to Kafka topics. Each event type becomes
the topic name for easy filtering and consumption.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.infrastructure.adapters.resilience import CircuitBreakerOpenException

if TYPE_CHECKING:
    from src.domain.shared_kernel import DomainEvent, Logger
    from src.infrastructure.adapters.resilience import CircuitBreaker
    from src.infrastructure.external.kafka_client import KafkaClient


class KafkaEventDispatcher:
    """
    Event dispatcher that publishes domain events to Kafka.

    Features:
    - Circuit breaker protection for resilience
    - Automatic reconnection
    - Structured logging
    - Idempotent publishing
    """

    def __init__(
        self,
        client: KafkaClient,
        topic_prefix: str,
        logger: Logger,
        circuit_breaker: CircuitBreaker,
    ):
        self.client = client
        self.topic_prefix = topic_prefix
        self.logger = logger
        self._connected = False
        self._circuit_breaker = circuit_breaker

    @property
    def circuit_breaker_status(self) -> dict:
        """Get circuit breaker status for health checks."""
        return self._circuit_breaker.get_status()

    async def _ensure_connected(self) -> None:
        """Ensure connection to Kafka is established."""
        if not self._connected:
            await self.client.connect()
            self._connected = True

    def _get_topic_name(self, event_name: str) -> str:
        """Generate topic name from event name."""
        if self.topic_prefix:
            return f"{self.topic_prefix}.{event_name}"
        return event_name

    async def _do_publish(self, topic: str, key: str, message_body: bytes) -> None:
        """Internal method to publish a message."""
        await self._ensure_connected()
        await self.client.publish(
            topic=topic,
            key=key,
            message_body=message_body
        )

    async def dispatch(self, event: DomainEvent) -> None:
        """
        Dispatch a domain event to Kafka.

        Protected by circuit breaker - will fail fast if Kafka is down.
        Use the transactional outbox pattern as a fallback.

        Raises:
            CircuitBreakerOpenException: If circuit is open (Kafka unhealthy)
            EventDispatcherException: If publish fails
        """
        event_name = event.__class__.__name__
        topic = self._get_topic_name(event_name)

        message_body = json.dumps({
            "event_name": event_name,
            "payload": event.__dict__
        }, default=str).encode()

        event_id = getattr(event, 'id', None) or getattr(event, 'event_id', None)
        key = str(event_id) if event_id else event_name

        try:
            await self._circuit_breaker.execute(
                self._do_publish,
                topic=topic,
                key=key,
                message_body=message_body
            )
            self.logger.info(f"Dispatched event: {event_name} to topic: {topic}")

        except CircuitBreakerOpenException as e:
            self.logger.warning(
                f"Circuit breaker OPEN for Kafka. Event {event_name} not dispatched. "
                f"Retry in {e.time_remaining:.1f}s. Use outbox pattern for guaranteed delivery."
            )
            raise

        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import \
                EventDispatcherException
            self.logger.error(f"Failed to dispatch event {event_name}", exception=e)
            self._connected = False
            raise EventDispatcherException(
                f"Failed to dispatch event {event_name}: {str(e)}",
                original_exception=e
            )

    async def dispatch_raw(self, event_type: str, payload: dict) -> None:
        """
        Dispatch a raw event from the outbox.

        Used by the OutboxProcessor to dispatch events that were stored
        as serialized data in the outbox table.
        """
        topic = self._get_topic_name(event_type)

        message_body = json.dumps({
            "event_name": event_type,
            "payload": payload
        }, default=str).encode()

        key = payload.get('id') or payload.get('event_id') or event_type

        try:
            await self._circuit_breaker.execute(
                self._do_publish,
                topic=topic,
                key=str(key),
                message_body=message_body
            )
            self.logger.info(f"Dispatched outbox event: {event_type} to topic: {topic}")

        except CircuitBreakerOpenException as e:
            self.logger.warning(
                f"Circuit breaker OPEN for Kafka. Outbox event {event_type} "
                f"will be retried later. Retry in {e.time_remaining:.1f}s."
            )
            raise

        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import \
                EventDispatcherException
            self.logger.error(f"Failed to dispatch outbox event {event_type}", exception=e)
            self._connected = False
            raise EventDispatcherException(
                f"Failed to dispatch outbox event {event_type}: {str(e)}",
                original_exception=e
            )

    async def is_healthy(self) -> bool:
        """Check if the dispatcher is healthy."""
        return not self._circuit_breaker.is_open

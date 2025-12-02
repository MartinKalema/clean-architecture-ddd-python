"""
RabbitMQ Event Dispatcher with Circuit Breaker protection.

The circuit breaker prevents cascading failures when RabbitMQ is unavailable,
allowing the system to fail fast and potentially use fallback mechanisms
(like the transactional outbox pattern).
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.infrastructure.adapters.resilience import CircuitBreakerOpenException

if TYPE_CHECKING:
    from src.domain.shared_kernel import DomainEvent, Logger
    from src.infrastructure.adapters.resilience import CircuitBreaker
    from src.infrastructure.external.rabbitmq_client import RabbitMQClient


class RabbitMQEventDispatcher:
    """
    Event dispatcher that publishes domain events to RabbitMQ.

    Features:
    - Circuit breaker protection for resilience (injected)
    - Automatic reconnection
    - Structured logging
    """

    def __init__(
        self,
        client: RabbitMQClient,
        exchange_name: str,
        logger: Logger,
        circuit_breaker: CircuitBreaker,
    ):
        self.client = client
        self.exchange_name = exchange_name
        self.logger = logger
        self._connected = False
        self._circuit_breaker = circuit_breaker

    @property
    def circuit_breaker_status(self) -> dict:
        """Get circuit breaker status for health checks."""
        return self._circuit_breaker.get_status()

    async def _ensure_connected(self) -> None:
        """Ensure connection to RabbitMQ is established."""
        if not self._connected:
            await self.client.connect(self.exchange_name)
            self._connected = True

    async def _do_publish(self, routing_key: str, message_body: bytes) -> None:
        """Internal method to publish a message."""
        await self._ensure_connected()
        await self.client.publish(
            routing_key=routing_key,
            message_body=message_body
        )

    async def dispatch(self, event: DomainEvent) -> None:
        """
        Dispatch a domain event to RabbitMQ.

        Protected by circuit breaker - will fail fast if RabbitMQ is down.
        Use the transactional outbox pattern as a fallback.

        Raises:
            CircuitBreakerOpenException: If circuit is open (RabbitMQ unhealthy)
            EventDispatcherException: If publish fails
        """
        message_body = json.dumps({
            "event_name": event.__class__.__name__,
            "payload": event.__dict__
        }, default=str).encode()

        event_name = event.__class__.__name__

        try:
            # Execute with circuit breaker protection
            await self._circuit_breaker.execute(
                self._do_publish,
                routing_key=event_name,
                message_body=message_body
            )
            self.logger.info(f"Dispatched event: {event_name}")

        except CircuitBreakerOpenException as e:
            # Circuit is open - fail fast
            self.logger.warning(
                f"Circuit breaker OPEN for RabbitMQ. Event {event_name} not dispatched. "
                f"Retry in {e.time_remaining:.1f}s. Use outbox pattern for guaranteed delivery."
            )
            raise

        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import (
                EventDispatcherException,
            )
            self.logger.error(f"Failed to dispatch event {event_name}", exception=e)
            # Mark connection as potentially stale
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

        Protected by circuit breaker for resilience.
        """
        message_body = json.dumps({
            "event_name": event_type,
            "payload": payload
        }, default=str).encode()

        try:
            await self._circuit_breaker.execute(
                self._do_publish,
                routing_key=event_type,
                message_body=message_body
            )
            self.logger.info(f"Dispatched outbox event: {event_type}")

        except CircuitBreakerOpenException as e:
            self.logger.warning(
                f"Circuit breaker OPEN for RabbitMQ. Outbox event {event_type} "
                f"will be retried later. Retry in {e.time_remaining:.1f}s."
            )
            raise

        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import (
                EventDispatcherException,
            )
            self.logger.error(f"Failed to dispatch outbox event {event_type}", exception=e)
            self._connected = False
            raise EventDispatcherException(
                f"Failed to dispatch outbox event {event_type}: {str(e)}",
                original_exception=e
            )

    async def is_healthy(self) -> bool:
        """
        Check if the dispatcher is healthy.

        Returns False if circuit breaker is open (RabbitMQ is down).
        """
        return not self._circuit_breaker.is_open

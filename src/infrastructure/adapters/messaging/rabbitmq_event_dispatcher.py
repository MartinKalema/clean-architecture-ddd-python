import json

from src.infrastructure.external.rabbitmq_client import RabbitMQClient
from src.domain.shared_kernel import DomainEvent, Logger


class RabbitMQEventDispatcher:
    def __init__(self, client: RabbitMQClient, exchange_name: str, logger: Logger):
        self.client = client
        self.exchange_name = exchange_name
        self.logger = logger
        self._connected = False

    async def _ensure_connected(self) -> None:
        """Ensure connection to RabbitMQ is established."""
        if not self._connected:
            await self.client.connect(self.exchange_name)
            self._connected = True

    async def dispatch(self, event: DomainEvent) -> None:
        """Dispatch a domain event to RabbitMQ."""
        message_body = json.dumps({
            "event_name": event.__class__.__name__,
            "payload": event.__dict__
        }, default=str).encode()

        event_name = event.__class__.__name__

        try:
            await self._ensure_connected()
            await self.client.publish(
                routing_key=event_name,
                message_body=message_body
            )
            self.logger.info(f"Dispatched event: {event_name}")
        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import EventDispatcherException
            self.logger.error(f"Failed to dispatch event {event_name}", exception=e)
            raise EventDispatcherException(f"Failed to dispatch event {event_name}: {str(e)}", original_exception=e)

    async def dispatch_raw(self, event_type: str, payload: dict) -> None:
        """
        Dispatch a raw event from the outbox.

        Used by the OutboxProcessor to dispatch events that were stored
        as serialized data in the outbox table.
        """
        message_body = json.dumps({
            "event_name": event_type,
            "payload": payload
        }, default=str).encode()

        try:
            await self._ensure_connected()
            await self.client.publish(
                routing_key=event_type,
                message_body=message_body
            )
            self.logger.info(f"Dispatched outbox event: {event_type}")
        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import EventDispatcherException
            self.logger.error(f"Failed to dispatch outbox event {event_type}", exception=e)
            raise EventDispatcherException(f"Failed to dispatch outbox event {event_type}: {str(e)}", original_exception=e)

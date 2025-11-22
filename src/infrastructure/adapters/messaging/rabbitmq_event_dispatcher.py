from src.infrastructure.external.rabbitmq_client import RabbitMQClient
from src.domain.events.domain_event import DomainEvent
from src.domain.interfaces.logger import Logger
import json

class RabbitMQEventDispatcher:
    def __init__(self, client: RabbitMQClient, exchange_name: str, logger: Logger):
        self.client = client
        self.exchange_name = exchange_name
        self.logger = logger

    async def dispatch(self, event: DomainEvent) -> None:
        message_body = json.dumps({
            "event_name": event.__class__.__name__,
            "payload": event.__dict__
        }, default=str).encode()

        event_name = event.__class__.__name__

        try:
            await self.client.publish(
                exchange_name=self.exchange_name,
                routing_key=event_name,
                message=message_body
            )
            self.logger.info(f"[RabbitMQAdapter] Dispatched event: {event_name}")
        except Exception as e:
            from src.infrastructure.exceptions.infrastructure_exceptions import EventDispatcherException
            self.logger.error(f"Failed to dispatch event {event_name}", exception=e)
            raise EventDispatcherException(f"Failed to dispatch event {event_name}: {str(e)}", original_exception=e)

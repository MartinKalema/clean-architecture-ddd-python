from src.infrastructure.external.rabbitmq_client import RabbitMQClient
from src.domain.events.domain_event import DomainEvent
import json

class RabbitMQEventDispatcher:
    def __init__(self, client: RabbitMQClient, exchange_name: str = "domain_events"):
        self.client = client
        self.exchange_name = exchange_name

    async def dispatch(self, event: DomainEvent) -> None:
        # Ensure client is connected (idempotent in client usually, or handled by lifecycle)
        await self.client.connect(self.exchange_name)
        
        message_body = json.dumps({
            "event_name": event.__class__.__name__,
            "payload": event.__dict__
        }, default=str).encode()

        await self.client.publish(
            routing_key=event.__class__.__name__,
            message_body=message_body
        )
        print(f"[RabbitMQAdapter] Dispatched event: {event.__class__.__name__}")

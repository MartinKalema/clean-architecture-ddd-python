from typing import Protocol
from src.domain.events.domain_event import DomainEvent

class EventDispatcher(Protocol):
    async def dispatch(self, event: DomainEvent) -> None:
        ...

"""
Event Dispatcher - Infrastructure implementation.

Implements: IEventDispatcher

Routes domain events to subscribed application-layer event handlers.
Subscriptions are injected by the composition root (the container), which
maps each domain event type to the handlers that react to it.

In this architecture reliability comes from the transactional outbox and
Kafka (at-least-once delivery); this dispatcher is only the last hop —
in-process routing inside the event worker after a message is consumed.

Handler failures are logged and isolated: Kafka has already delivered the
message, so one failing handler must not prevent the other handlers of the
same event from running. Handlers must be idempotent, because at-least-once
delivery means an event can be dispatched more than once.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Type

if TYPE_CHECKING:
    from src.domain.shared_kernel import DomainEvent, IEventHandler, ILogger


class EventDispatcher:
    """Routes domain events to subscribed handlers. dispatch() never raises."""

    def __init__(
        self,
        subscriptions: Optional[Dict[Type["DomainEvent"], List["IEventHandler"]]] = None,
        logger: Optional[ILogger] = None,
    ):
        self.logger = logger
        self._handlers: Dict[Type["DomainEvent"], List["IEventHandler"]] = {
            event_type: list(handlers)
            for event_type, handlers in (subscriptions or {}).items()
        }

    def subscribe(
        self, event_type: Type["DomainEvent"], handler: "IEventHandler"
    ) -> None:
        """Register a handler for an event type (or a base class of one)."""
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(self, event: "DomainEvent") -> None:
        """Invoke every handler subscribed to this event's type."""
        for subscribed_type, handlers in self._handlers.items():
            if not isinstance(event, subscribed_type):
                continue
            for handler in handlers:
                try:
                    await handler.handle(event)
                except Exception as e:
                    if self.logger:
                        self.logger.error(
                            f"Event handler failed for {event.event_type} "
                            f"(event_id={event.event_id})",
                            exception=e,
                        )

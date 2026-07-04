"""
Event Dispatcher - Infrastructure implementation.

Implements: IEventDispatcher

Routes domain events to subscribed application-layer event handlers.
Subscriptions are injected by the composition root (the container), which
maps each domain event type to the handlers that react to it.

Error contract: every subscribed handler gets a chance to run on every
dispatch — one failing handler never blocks the others. But failures are
not swallowed: if any handler failed, dispatch() raises after the loop so
the delivery layer (Kafka consumer) retries the message with backoff and
dead-letters it when retries are exhausted. Post-pivot steps are promises
(the loan exists, so the email must eventually send); a transient outage
must trigger redelivery, not silent loss.

This makes handler idempotency mandatory: a retried message re-runs the
handlers that already succeeded. Handlers that detect a permanently
unprocessable situation should catch it themselves and escalate instead
of raising, so it is not pointlessly retried.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Type

from src.infrastructure.exceptions import EventDispatcherException

if TYPE_CHECKING:
    from src.domain.shared_kernel import DomainEvent, IEventHandler, ILogger


class EventDispatcher:
    """Routes domain events to subscribed handlers."""

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
        """
        Invoke every handler subscribed to this event's type.

        All handlers run even if some fail; raises after the loop if any
        failed, so the delivery layer retries (and eventually dead-letters)
        the message.
        """
        failures: List[Exception] = []

        for subscribed_type, handlers in self._handlers.items():
            if not isinstance(event, subscribed_type):
                continue
            for handler in handlers:
                try:
                    await handler.handle(event)
                except Exception as e:
                    failures.append(e)
                    if self.logger:
                        self.logger.error(
                            f"Event handler {type(handler).__name__} failed "
                            f"for {event.event_type} (event_id={event.event_id})",
                            exception=e,
                        )

        if failures:
            raise EventDispatcherException(
                f"{len(failures)} handler(s) failed for {event.event_type} "
                f"(event_id={event.event_id}); message will be retried",
                original_exception=failures[0],
            )

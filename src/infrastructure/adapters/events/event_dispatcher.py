"""
Event Dispatcher - Infrastructure implementation.

Implements: IEventDispatcher

Routes domain events to subscribed application-layer event handlers.
Subscriptions are injected by the composition root (the container), which
maps each domain event type to the handlers that react to it.

Error contract: every subscribed handler gets a chance to run on every
dispatch — one failing handler never blocks the others. But failures are
not swallowed: if any handler failed, dispatch() raises after the loop so
the delivery layer (Kafka consumer) applies the event's retry policy.
Committed workflow transitions retry until they converge; optional consumers
use bounded retries and dead-lettering.

The durable per-handler inbox skips handlers whose completion was recorded.
Handlers must still be idempotent across the unavoidable crash window between
their own side effect and the separate inbox-completion transaction.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Dict, List, Optional, Type, cast

from src.application.ports import EventDeliveryIdentity
from src.domain.shared_kernel import caused_by
from src.infrastructure.adapters.events.delivery_store import (
    HandlerInbox,
    InboxClaimStatus,
)
from src.infrastructure.adapters.events.event_registry import contract_for_event, serialize_event
from src.infrastructure.exceptions import EventDispatcherException

if TYPE_CHECKING:
    from src.application.ports import IEventHandler, ILogger
    from src.domain.shared_kernel import DomainEvent

    HandlerRegistration = IEventHandler | Callable[[], IEventHandler]


class EventDispatcher:
    """Routes domain events to subscribed handlers."""

    def __init__(
        self,
        subscriptions: Optional[
            Dict[Type["DomainEvent"], List["HandlerRegistration"]]
        ] = None,
        logger: Optional[ILogger] = None,
        inbox: Optional[HandlerInbox] = None,
    ):
        self.logger = logger
        self._inbox = inbox
        self._handlers: Dict[
            Type["DomainEvent"], List["HandlerRegistration"]
        ] = {
            event_type: list(handlers)
            for event_type, handlers in (subscriptions or {}).items()
        }

    def subscribe(
        self, event_type: Type["DomainEvent"], handler: "IEventHandler"
    ) -> None:
        """Register a handler for an event type (or a base class of one)."""
        self._handlers.setdefault(event_type, []).append(handler)

    async def dispatch(
        self,
        event: "DomainEvent",
        delivery_identity: EventDeliveryIdentity | None = None,
    ) -> None:
        """
        Invoke every handler subscribed to this event's type.

        All handlers run even if some fail; raises after the loop if any
        failed, so the delivery layer applies that event's retry policy.
        """
        failures: List[Exception] = []

        for subscribed_type, handlers in self._handlers.items():
            if not isinstance(event, subscribed_type):
                continue
            for registration in handlers:
                # Production subscriptions are provider delegates. Resolve a
                # fresh application handler graph for every delivery so its
                # mutable UoW/session cannot be shared by concurrent workers.
                handler = _resolve_handler(registration)
                handler_name = _handler_name(handler)
                claim_token: str | None = None
                if self._inbox is not None:
                    try:
                        identity = delivery_identity or _current_identity(event)
                        claim = await self._inbox.claim(
                            event_id=event.event_id,
                            handler_name=handler_name,
                            contract_name=identity.contract_name,
                            contract_version=identity.contract_version,
                            payload_hash=identity.payload_hash,
                            correlation_id=event.correlation_id,
                            causation_id=event.causation_id,
                        )
                    except Exception as error:
                        failures.append(error)
                        self._log_failure(handler_name, event, error)
                        continue
                    if claim.status == InboxClaimStatus.PROCESSED:
                        if self.logger:
                            self.logger.debug(
                                f"Skipping processed event {event.event_id} "
                                f"for {handler_name}"
                            )
                        continue
                    if claim.status == InboxClaimStatus.BUSY:
                        busy_error = RuntimeError(
                            f"Event {event.event_id} is already leased by {handler_name}"
                        )
                        failures.append(busy_error)
                        self._log_failure(handler_name, event, busy_error)
                        continue
                    claim_token = claim.token
                    if not claim_token:
                        token_error = RuntimeError(
                            f"Inbox returned a claimed event without a fencing "
                            f"token for {event.event_id}/{handler_name}"
                        )
                        failures.append(token_error)
                        self._log_failure(handler_name, event, token_error)
                        continue

                try:
                    with caused_by(event):
                        await handler.handle(event)
                except Exception as e:
                    failures.append(e)
                    self._log_failure(handler_name, event, e)
                    if self._inbox is not None and claim_token is not None:
                        try:
                            await self._inbox.fail(
                                event_id=event.event_id,
                                handler_name=handler_name,
                                token=claim_token,
                                error=e,
                            )
                        except Exception as inbox_error:
                            failures.append(inbox_error)
                            self._log_failure(handler_name, event, inbox_error)
                else:
                    if self._inbox is not None and claim_token is not None:
                        try:
                            await self._inbox.complete(
                                event_id=event.event_id,
                                handler_name=handler_name,
                                token=claim_token,
                            )
                        except Exception as completion_error:
                            failures.append(completion_error)
                            self._log_failure(
                                handler_name, event, completion_error
                            )

        if failures:
            raise EventDispatcherException(
                f"{len(failures)} handler(s) failed for {event.event_type} "
                f"(event_id={event.event_id}); message will be retried",
                original_exception=failures[0],
            )

    def _log_failure(
        self, handler_name: str, event: "DomainEvent", error: Exception
    ) -> None:
        if self.logger:
            self.logger.error(
                f"Event handler {handler_name} failed for {event.event_type} "
                f"(event_id={event.event_id})",
                exception=error,
            )


def _handler_name(handler: "IEventHandler") -> str:
    explicit_name = getattr(handler, "inbox_consumer_name", None)
    if isinstance(explicit_name, str) and explicit_name.strip():
        return explicit_name
    handler_type = type(handler)
    return f"{handler_type.__module__}.{handler_type.__qualname__}"


def _resolve_handler(registration: "HandlerRegistration") -> "IEventHandler":
    if hasattr(registration, "handle"):
        return cast("IEventHandler", registration)
    if callable(registration):
        handler = registration()
        if hasattr(handler, "handle"):
            return handler
    raise TypeError("Event subscription must resolve to an event handler")


def _current_identity(event: "DomainEvent") -> EventDeliveryIdentity:
    import hashlib

    contract = contract_for_event(event)
    payload = serialize_event(event)
    return EventDeliveryIdentity(
        contract_name=contract.qualified_name,
        contract_version=contract.version,
        payload_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )

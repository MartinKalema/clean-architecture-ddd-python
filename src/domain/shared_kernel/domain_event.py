"""
DomainEvent base class for all domain events.

Domain Events represent something that happened in the domain that domain experts
care about. They are used to:
1. Communicate between aggregates within a bounded context
2. Communicate between bounded contexts (integration events)
3. Maintain eventual consistency across the system
"""
import uuid
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterator, Optional

from .exceptions import ValidationException
from .time import require_utc_datetime


_correlation_context: ContextVar[Optional[str]] = ContextVar(
    "domain_event_correlation_id", default=None
)
_causation_context: ContextVar[Optional[str]] = ContextVar(
    "domain_event_causation_id", default=None
)


@dataclass(frozen=True)
class DomainEvent:
    """
    Base class for all domain events.

    Attributes:
        event_id: Unique identifier for this event instance
        occurred_at: Timestamp when the event occurred
        correlation_id: ID shared by every event in one workflow
        causation_id: ID of the event that directly caused this event
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc), kw_only=True
    )
    correlation_id: Optional[str] = field(
        default_factory=_correlation_context.get, kw_only=True
    )
    causation_id: Optional[str] = field(
        default_factory=_causation_context.get, kw_only=True
    )

    def __post_init__(self) -> None:
        event_id = _event_identity(self.event_id, "event_id")
        correlation_id = (
            _event_identity(self.correlation_id, "correlation_id")
            if self.correlation_id is not None
            else event_id
        )
        causation_id = (
            _event_identity(self.causation_id, "causation_id")
            if self.causation_id is not None
            else None
        )
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "causation_id", causation_id)
        # A root event starts its own trace. Events created while handling it
        # inherit the trace and record the source event as their direct cause.
        object.__setattr__(
            self,
            "occurred_at",
            require_utc_datetime(self.occurred_at, "occurred_at"),
        )

    @property
    def event_type(self) -> str:
        """Return the event type name for routing/serialization."""
        return self.__class__.__name__


@contextmanager
def caused_by(event: DomainEvent) -> Iterator[None]:
    """Propagate correlation and causation through an event handler call."""
    correlation_token = _correlation_context.set(
        event.correlation_id or event.event_id
    )
    causation_token = _causation_context.set(event.event_id)
    try:
        yield
    finally:
        _causation_context.reset(causation_token)
        _correlation_context.reset(correlation_token)


def _event_identity(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValidationException(f"{field_name} must be a string")
    normalized = value.strip()
    if (
        not 1 <= len(normalized) <= 128
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", normalized) is None
    ):
        raise ValidationException(
            f"{field_name} must be 1-128 URL/log-safe characters"
        )
    return normalized

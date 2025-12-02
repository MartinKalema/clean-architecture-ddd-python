"""
DomainEvent base class for all domain events.

Domain Events represent something that happened in the domain that domain experts
care about. They are used to:
1. Communicate between aggregates within a bounded context
2. Communicate between bounded contexts (integration events)
3. Maintain eventual consistency across the system
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class DomainEvent:
    """
    Base class for all domain events.

    Attributes:
        event_id: Unique identifier for this event instance
        occurred_at: Timestamp when the event occurred
        correlation_id: Optional ID to correlate related events
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()), kw_only=True)
    occurred_at: datetime = field(default_factory=datetime.now, kw_only=True)
    correlation_id: Optional[str] = field(default=None, kw_only=True)

    @property
    def event_type(self) -> str:
        """Return the event type name for routing/serialization."""
        return self.__class__.__name__

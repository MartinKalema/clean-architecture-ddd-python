"""
AggregateRoot base class for all aggregates in all bounded contexts.

An Aggregate is a cluster of domain objects that can be treated as a single unit.
The AggregateRoot is the entry point to the aggregate - all access to the aggregate
must go through the root.

Key responsibilities:
- Maintains list of domain events raised by the aggregate
- Ensures consistency boundaries within the aggregate
- Provides optimistic locking via version field
"""
from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .domain_event import DomainEvent


@dataclass
class AggregateRoot:
    """Base class for all aggregate roots across bounded contexts."""

    _domain_events: List["DomainEvent"] = field(
        default_factory=list, init=False, repr=False
    )
    _version: int = field(default=0, init=False, repr=False)

    @property
    def version(self) -> int:
        """Current version for optimistic locking."""
        return self._version

    def _increment_version(self) -> None:
        """Increment version after successful update."""
        self._version += 1

    def add_event(self, event: "DomainEvent") -> None:
        """Register a domain event to be dispatched after commit."""
        self._domain_events.append(event)

    def clear_events(self) -> None:
        """Clear all pending domain events (called after dispatch)."""
        self._domain_events.clear()

    def get_domain_events(self) -> List["DomainEvent"]:
        """Return a copy of pending domain events."""
        return list(self._domain_events)

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
from contextlib import contextmanager
from dataclasses import dataclass, field, fields
from functools import wraps
from typing import TYPE_CHECKING, Callable, Iterator, List, TypeVar

if TYPE_CHECKING:
    from .domain_event import DomainEvent

T = TypeVar("T")


@dataclass
class AggregateRoot:
    """Base class for all aggregate roots across bounded contexts."""

    _domain_events: List["DomainEvent"] = field(
        default_factory=list, init=False, repr=False
    )
    _version: int = field(default=0, init=False, repr=False)
    _state_fields: frozenset[str] = field(
        default_factory=frozenset, init=False, repr=False
    )
    _mutation_depth: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Seal public aggregate state after construction or hydration."""
        object.__setattr__(
            self,
            "_state_fields",
            frozenset(
                model_field.name
                for model_field in fields(self)
                if not model_field.name.startswith("_")
            ),
        )

    def __setattr__(self, name: str, value) -> None:
        protected: frozenset[str] = getattr(
            self, "_state_fields", frozenset()
        )
        if name in protected and getattr(self, "_mutation_depth", 0) == 0:
            raise AttributeError(
                f"{type(self).__name__}.{name} is read-only; "
                "use an aggregate transition"
            )
        object.__setattr__(self, name, value)

    @contextmanager
    def _allow_state_changes(self) -> Iterator[None]:
        object.__setattr__(self, "_mutation_depth", self._mutation_depth + 1)
        try:
            yield
        finally:
            object.__setattr__(self, "_mutation_depth", self._mutation_depth - 1)

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


def aggregate_transition(method: Callable[..., T]) -> Callable[..., T]:
    """Authorize public state mutation only inside aggregate behavior."""

    @wraps(method)
    def guarded(self: AggregateRoot, *args, **kwargs):
        with self._allow_state_changes():
            return method(self, *args, **kwargs)

    return guarded

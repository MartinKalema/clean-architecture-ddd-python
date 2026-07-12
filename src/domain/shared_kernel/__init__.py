"""
Shared Kernel - Types shared across all bounded contexts.

In DDD, a Shared Kernel is a subset of the domain model that two or more
bounded contexts agree to share. Changes to the shared kernel require
coordination between all teams that use it.
"""
from .aggregate_root import AggregateRoot, aggregate_transition
from .domain_event import DomainEvent, caused_by
from .exceptions import (
    DomainException,
    EmptyValueException,
    InvalidEmailException,
    ValidationException,
)
from .value_objects import EmailAddress
from .time import require_utc_datetime

__all__ = [
    "AggregateRoot",
    "aggregate_transition",
    "DomainEvent",
    "caused_by",
    "EmailAddress",
    "DomainException",
    "ValidationException",
    "InvalidEmailException",
    "EmptyValueException",
    "require_utc_datetime",
]

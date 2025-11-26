"""
Shared Kernel - Types shared across all bounded contexts.

In DDD, a Shared Kernel is a subset of the domain model that two or more
bounded contexts agree to share. Changes to the shared kernel require
coordination between all teams that use it.

This module contains:
- Base classes (AggregateRoot, Entity, ValueObject)
- Common value objects (EmailAddress, Money)
- Domain event base class
"""
from .aggregate_root import AggregateRoot
from .domain_event import DomainEvent
from .value_objects import EmailAddress

__all__ = ["AggregateRoot", "DomainEvent", "EmailAddress"]

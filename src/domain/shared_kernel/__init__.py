"""
Shared Kernel - Types shared across all bounded contexts.

In DDD, a Shared Kernel is a subset of the domain model that two or more
bounded contexts agree to share. Changes to the shared kernel require
coordination between all teams that use it.
"""
from .aggregate_root import AggregateRoot
from .domain_event import DomainEvent
from .exceptions import (
    DomainException,
    EmailDeliveryException,
    EmptyValueException,
    InvalidEmailException,
    ValidationException,
)
from .interfaces import (
    ICache,
    IConfigurationProvider,
    IEmailService,
    IEventDispatcher,
    IEventHandler,
    ILogger,
)
from .value_objects import EmailAddress

__all__ = [
    "AggregateRoot",
    "DomainEvent",
    "EmailAddress",
    "ICache",
    "IConfigurationProvider",
    "IEmailService",
    "IEventDispatcher",
    "IEventHandler",
    "ILogger",
    "DomainException",
    "EmailDeliveryException",
    "ValidationException",
    "InvalidEmailException",
    "EmptyValueException",
]

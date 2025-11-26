"""
Shared Kernel - Types shared across all bounded contexts.

In DDD, a Shared Kernel is a subset of the domain model that two or more
bounded contexts agree to share. Changes to the shared kernel require
coordination between all teams that use it.
"""
from .aggregate_root import AggregateRoot
from .domain_event import DomainEvent
from .value_objects import EmailAddress
from .interfaces import Logger, EventDispatcher, EmailService, TemplateRenderer
from .email_template import EmailTemplate

__all__ = [
    "AggregateRoot",
    "DomainEvent",
    "EmailAddress",
    "Logger",
    "EventDispatcher",
    "EmailService",
    "TemplateRenderer",
    "EmailTemplate",
]

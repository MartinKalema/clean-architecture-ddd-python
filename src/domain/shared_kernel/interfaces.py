"""
Shared interfaces used across all bounded contexts.

These are infrastructure ports that any context might need.
"""
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol, Type

if TYPE_CHECKING:
    from .domain_event import DomainEvent


class ILogger(Protocol):
    def info(self, message: str) -> None:
        ...

    def error(self, message: str, exception: Optional[Exception] = None) -> None:
        ...

    def warning(self, message: str) -> None:
        ...

    def debug(self, message: str) -> None:
        ...


class IEventHandler(Protocol):
    """A handler that reacts to a single type of domain event."""

    async def handle(self, event: Any) -> None:
        ...


class IEventDispatcher(Protocol):
    """
    Dispatches domain events to subscribed handlers.

    Contract: every subscribed handler runs on every dispatch (one failure
    does not block the others), but if any handler failed, dispatch()
    raises so the delivery layer can retry the message and dead-letter it
    when retries are exhausted. Handlers must therefore be idempotent —
    a retry re-runs handlers that already succeeded — and should catch
    permanently unprocessable situations themselves (escalate, don't
    raise) so they are not pointlessly retried.
    """

    def subscribe(
        self, event_type: Type["DomainEvent"], handler: "IEventHandler"
    ) -> None:
        ...

    async def dispatch(self, event: "DomainEvent") -> None:
        ...


class IEmailService(Protocol):
    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        ...


class ITemplateRenderer(Protocol):
    def render(self, template: Any, context: Dict[str, Any]) -> str:
        ...


class IConfigurationProvider(Protocol):
    def get(self, key: str, default: Any = None) -> Any:
        ...

    def get_all(self) -> Dict[str, Any]:
        ...

    def watch(self, key: str, callback: Any) -> None:
        ...

    def close(self) -> None:
        ...


class ICache(Protocol):
    def get(self, key: str) -> Optional[Any]:
        ...

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        ...

    def delete(self, key: str) -> bool:
        ...

    def invalidate_entity(self, entity_type: str, entity_id: str) -> None:
        ...

    def invalidate_all(self, entity_type: str) -> None:
        ...

    @property
    def is_enabled(self) -> bool:
        ...

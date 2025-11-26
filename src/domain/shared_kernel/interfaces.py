"""
Shared interfaces used across all bounded contexts.

These are infrastructure ports that any context might need.
"""
from typing import Protocol, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .domain_event import DomainEvent


class Logger(Protocol):
    def info(self, message: str) -> None:
        ...

    def error(self, message: str, exception: Exception = None) -> None:
        ...

    def warning(self, message: str) -> None:
        ...

    def debug(self, message: str) -> None:
        ...


class EventDispatcher(Protocol):
    async def dispatch(self, event: "DomainEvent") -> None:
        ...


class EmailService(Protocol):
    async def send_email(self, to_email: str, subject: str, content: str) -> None:
        ...


class TemplateRenderer(Protocol):
    def render(self, template: Any, context: Dict[str, Any]) -> str:
        ...

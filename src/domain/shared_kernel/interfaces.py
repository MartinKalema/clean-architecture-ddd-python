"""
Shared interfaces used across all bounded contexts.

These are infrastructure ports that any context might need.
"""
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol

if TYPE_CHECKING:
    from .domain_event import DomainEvent


class Logger(Protocol):
    def info(self, message: str) -> None:
        ...

    def error(self, message: str, exception: Optional[Exception] = None) -> None:
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


class ConfigurationProvider(Protocol):
    """Interface for configuration providers (file, etcd, consul, etc.)."""

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key."""
        ...

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        ...

    def watch(self, key: str, callback: Any) -> None:
        """Watch a key for changes and call callback when it changes."""
        ...

    def close(self) -> None:
        """Close the provider and release resources."""
        ...

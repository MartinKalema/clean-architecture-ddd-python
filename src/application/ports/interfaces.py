"""Technology-facing ports owned by the application layer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Optional,
    Protocol,
    Type,
    TypeVar,
)

if TYPE_CHECKING:
    from src.domain.shared_kernel import DomainEvent

T = TypeVar("T")


@dataclass(frozen=True)
class EventDeliveryIdentity:
    """Immutable source-envelope identity used by durable handler inboxes."""

    contract_name: str
    contract_version: int
    payload_hash: str


class ILogger(Protocol):
    def info(self, message: str) -> None: ...

    def error(
        self, message: str, exception: Optional[Exception] = None
    ) -> None: ...

    def warning(self, message: str) -> None: ...

    def debug(self, message: str) -> None: ...


class IEventHandler(Protocol):
    """Application reaction to one integration/domain event."""

    async def handle(self, event: Any) -> None: ...


class IEventDispatcher(Protocol):
    """Routes a delivered event to its application handlers."""

    def subscribe(
        self, event_type: Type["DomainEvent"], handler: IEventHandler
    ) -> None: ...

    async def dispatch(
        self,
        event: "DomainEvent",
        delivery_identity: EventDeliveryIdentity | None = None,
    ) -> None: ...


class IEmailService(Protocol):
    async def send_email(
        self,
        to_email: str,
        subject: str,
        content: str,
        delivery_id: str | None = None,
    ) -> None: ...


class IConfigurationProvider(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...

    def get_all(self) -> Dict[str, Any]: ...

    def watch(self, key: str, callback: Any) -> None: ...

    def close(self) -> None: ...


class ICache(Protocol):
    async def get(self, key: str) -> Optional[Any]: ...

    async def set(
        self, key: str, value: Any, ttl: Optional[int] = None
    ) -> bool: ...

    async def delete(self, key: str) -> bool: ...

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        ttl: Optional[int] = None,
    ) -> T: ...

    async def invalidate_entity(
        self, entity_type: str, entity_id: str
    ) -> bool: ...

    async def invalidate_all(self, entity_type: str) -> bool: ...

    @property
    def is_enabled(self) -> bool: ...

    def build_key(self, *parts: Any) -> str: ...

    def build_list_key(self, entity_type: str, **filters: Any) -> str: ...

    def build_count_key(self, entity_type: str, **filters: Any) -> str: ...

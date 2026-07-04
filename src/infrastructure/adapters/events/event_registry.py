"""
Domain event (de)serialization for the transactional outbox.

The outbox stores events as JSON payloads; the event worker reconstructs
typed domain events from those payloads before dispatching them to
application-layer handlers. The registry below is the single place that
maps an event type name to its domain class.
"""
import json
from dataclasses import asdict, fields
from datetime import datetime
from typing import Any, Dict, Optional, Type, Union, get_args, get_origin, get_type_hints

from src.domain.catalog.events.catalog_events import (
    BookAddedToCatalog,
    BookRemovedFromCatalog,
    CatalogBookBorrowed,
    CatalogBookReleased,
    CatalogBookReserved,
    CatalogBookReturned,
)
from src.domain.lending.events.lending_events import (
    BookOverdue,
    LoanCompleted,
    LoanCreated,
    LoanExtended,
)
from src.domain.patron.events.patron_events import (
    PatronRegistered,
    PatronReinstated,
    PatronSuspended,
)
from src.domain.shared_kernel import DomainEvent

EVENT_TYPES: Dict[str, Type[DomainEvent]] = {
    cls.__name__: cls
    for cls in (
        BookAddedToCatalog,
        BookRemovedFromCatalog,
        CatalogBookBorrowed,
        CatalogBookReleased,
        CatalogBookReserved,
        CatalogBookReturned,
        LoanCreated,
        LoanCompleted,
        LoanExtended,
        BookOverdue,
        PatronRegistered,
        PatronSuspended,
        PatronReinstated,
    )
}


def serialize_event(event: DomainEvent) -> str:
    """Serialize a domain event to a JSON payload, including its type."""
    data = asdict(event)
    data["event_type"] = event.event_type
    return json.dumps(data, default=_encode_value)


def deserialize_event(payload: Dict[str, Any]) -> Optional[DomainEvent]:
    """
    Reconstruct a typed domain event from an outbox payload.

    Returns None for unknown event types so the consumer can log and skip
    events published by a newer (or older) version of the application.
    """
    event_type = payload.get("event_type")
    cls = EVENT_TYPES.get(event_type) if event_type else None
    if cls is None:
        return None

    hints = get_type_hints(cls)
    kwargs = {}
    for f in fields(cls):
        if f.name not in payload:
            continue
        value = payload[f.name]
        if value is not None and _is_datetime(hints.get(f.name)):
            value = datetime.fromisoformat(value)
        kwargs[f.name] = value
    return cls(**kwargs)


def _encode_value(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _is_datetime(field_type: Any) -> bool:
    if field_type is datetime:
        return True
    if get_origin(field_type) is Union:
        return datetime in get_args(field_type)
    return False

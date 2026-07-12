"""Stable, versioned wire contracts for domain-event delivery.

Python class names are an implementation detail.  Kafka payloads use an
explicit namespace/name/version envelope, while this registry retains a
bounded upcast path for flat payloads already waiting in the outbox.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from types import UnionType
from typing import (
    Any,
    Callable,
    Dict,
    Type,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from src.application.events import LegacyWorkflowCompensated
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
    LoanCancelled,
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

WIRE_ENVELOPE_VERSION = 1
_METADATA_FIELDS = {
    "event_id",
    "occurred_at",
    "correlation_id",
    "causation_id",
}
_REFERENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_RESERVATION_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_EMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}\Z"
)


class EventContractError(ValueError):
    """Base class for payloads that cannot safely enter domain dispatch."""

    def __init__(
        self,
        message: str,
        *,
        event_id: str | None = None,
        contract_name: str | None = None,
        contract_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.event_id = event_id
        self.contract_name = contract_name
        self.contract_version = contract_version


class UnsupportedEventContractError(EventContractError):
    """The event name or version is not understood by this deployment."""


class InvalidEventEnvelopeError(EventContractError):
    """A known contract has malformed metadata or data."""


@dataclass(frozen=True)
class EventContract:
    namespace: str
    name: str
    version: int
    event_class: Type[DomainEvent]

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}.{self.name}"


def _contract(
    namespace: str,
    name: str,
    event_class: Type[DomainEvent],
    version: int = 1,
) -> EventContract:
    return EventContract(namespace, name, version, event_class)


EVENT_CONTRACTS = (
    _contract("library.catalog", "book-added", BookAddedToCatalog),
    _contract("library.catalog", "book-removed", BookRemovedFromCatalog),
    # v2 removes Catalog's precomputed return_due_date. Lending now derives
    # duration from the authoritative patron tier and publishes the final due
    # date in LoanCreated.
    _contract("library.catalog", "book-reserved", CatalogBookReserved, version=2),
    _contract("library.catalog", "book-borrowed", CatalogBookBorrowed, version=2),
    _contract("library.catalog", "book-released", CatalogBookReleased, version=2),
    _contract("library.catalog", "book-returned", CatalogBookReturned, version=2),
    _contract("library.lending", "loan-created", LoanCreated, version=2),
    _contract("library.lending", "loan-completed", LoanCompleted, version=2),
    _contract("library.lending", "loan-cancelled", LoanCancelled),
    _contract("library.lending", "loan-extended", LoanExtended),
    _contract("library.lending", "book-overdue", BookOverdue),
    _contract("library.patron", "patron-registered", PatronRegistered),
    _contract("library.patron", "patron-suspended", PatronSuspended),
    _contract("library.patron", "patron-reinstated", PatronReinstated),
    _contract(
        "library.migration",
        "workflow-compensated",
        LegacyWorkflowCompensated,
    ),
)

EVENT_TYPES: Dict[str, Type[DomainEvent]] = {
    # Immutable aliases for payloads persisted before namespaced contracts.
    # Never regenerate these from implementation class names: a Python rename
    # must not strand an old outbox or DLQ record.
    "BookAddedToCatalog": BookAddedToCatalog,
    "BookRemovedFromCatalog": BookRemovedFromCatalog,
    "CatalogBookReserved": CatalogBookReserved,
    "CatalogBookBorrowed": CatalogBookBorrowed,
    "CatalogBookReleased": CatalogBookReleased,
    "CatalogBookReturned": CatalogBookReturned,
    "LoanCreated": LoanCreated,
    "LoanCompleted": LoanCompleted,
    "LoanCancelled": LoanCancelled,
    "LoanExtended": LoanExtended,
    "BookOverdue": BookOverdue,
    "PatronRegistered": PatronRegistered,
    "PatronSuspended": PatronSuspended,
    "PatronReinstated": PatronReinstated,
    "LegacyWorkflowCompensated": LegacyWorkflowCompensated,
}
_CONTRACT_BY_CLASS = {
    contract.event_class: contract for contract in EVENT_CONTRACTS
}
_CONTRACT_BY_NAME = {
    contract.qualified_name: contract for contract in EVENT_CONTRACTS
}
if len(_CONTRACT_BY_CLASS) != len(EVENT_CONTRACTS):
    raise RuntimeError("A domain event class has more than one wire contract")
if len(_CONTRACT_BY_NAME) != len(EVENT_CONTRACTS):
    raise RuntimeError("A namespaced wire contract is registered more than once")


def _upcast_catalog_book_reserved_v1(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    # Keep the field while a mixed-version process still has the v1 domain
    # class; once the v2 class is deployed it is deliberately discarded.
    current_fields = {event_field.name for event_field in fields(CatalogBookReserved)}
    if "return_due_date" not in current_fields:
        result.pop("return_due_date", None)
    _require_upcast_fields(
        result,
        "reservation_id",
        "reservation_generation",
        "patron_id",
    )
    return result


def _upcast_with_required_fields(
    *required_fields: str,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def upcast(data: dict[str, Any]) -> dict[str, Any]:
        result = dict(data)
        _require_upcast_fields(result, *required_fields)
        return result

    return upcast


def _require_upcast_fields(data: dict[str, Any], *required_fields: str) -> None:
    missing = [name for name in required_fields if name not in data]
    if missing:
        raise InvalidEventEnvelopeError(
            "Legacy event cannot be correlated safely; missing field(s): "
            + ", ".join(missing)
        )


_UPCASTERS: dict[tuple[str, int], Callable[[dict[str, Any]], dict[str, Any]]] = {
    ("library.catalog.book-reserved", 1): _upcast_catalog_book_reserved_v1,
    ("library.catalog.book-borrowed", 1): _upcast_with_required_fields(
        "reservation_id",
        "reservation_generation",
        "patron_id",
        "loan_id",
    ),
    ("library.catalog.book-released", 1): _upcast_with_required_fields(
        "reservation_id",
        "reservation_generation",
        "patron_id",
    ),
    ("library.catalog.book-returned", 1): _upcast_with_required_fields(
        "loan_id",
        "reservation_id",
        "reservation_generation",
        "patron_id",
    ),
    ("library.lending.loan-created", 1): _upcast_with_required_fields(
        "reservation_id",
        "reservation_generation",
    ),
    ("library.lending.loan-completed", 1): _upcast_with_required_fields(
        "reservation_id",
        "reservation_generation",
    ),
}


def register_upcaster(
    contract_name: str,
    from_version: int,
    upcaster: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    """Register one deterministic data migration from N to N+1."""
    contract = _CONTRACT_BY_NAME.get(contract_name)
    if contract is None:
        raise ValueError(f"Unknown event contract: {contract_name}")
    if not isinstance(from_version, int) or isinstance(from_version, bool):
        raise ValueError("from_version must be an integer")
    if not 1 <= from_version < contract.version:
        raise ValueError(
            f"from_version must be between 1 and {contract.version - 1} "
            f"for {contract_name}"
        )
    if not callable(upcaster):
        raise TypeError("upcaster must be callable")
    key = (contract_name, from_version)
    if key in _UPCASTERS:
        raise ValueError(f"Upcaster already registered for {contract_name} v{from_version}")
    _UPCASTERS[key] = upcaster


def contract_for_event(event: DomainEvent) -> EventContract:
    try:
        return _CONTRACT_BY_CLASS[type(event)]
    except KeyError as error:
        raise UnsupportedEventContractError(
            f"No wire contract registered for {type(event).__name__}",
            event_id=event.event_id,
        ) from error


def outbox_type_for_event_class(event_class: Type[DomainEvent]) -> str:
    """Stable Debezium event-type header independent of Python class names."""
    try:
        contract = _CONTRACT_BY_CLASS[event_class]
    except KeyError as error:
        raise UnsupportedEventContractError(
            f"No wire contract registered for {event_class.__name__}"
        ) from error
    return f"{contract.qualified_name}.v{contract.version}"


def serialize_event(event: DomainEvent) -> str:
    """Serialize an event into the current namespaced wire envelope."""
    contract = contract_for_event(event)
    values = asdict(event)
    metadata = {name: values.pop(name, None) for name in _METADATA_FIELDS}
    # Validate outbound events too. Dataclass annotations are not enforced at
    # runtime, and emitting an invalid current-version contract would poison
    # every downstream consumer.
    _construct_event(contract, metadata, values)
    envelope = {
        "envelope_version": WIRE_ENVELOPE_VERSION,
        "contract": {
            "namespace": contract.namespace,
            "name": contract.name,
            "version": contract.version,
        },
        "metadata": metadata,
        "data": values,
    }
    return json.dumps(envelope, default=_encode_value, separators=(",", ":"))


def deserialize_event(payload: Dict[str, Any]) -> DomainEvent:
    """Validate, upcast, and reconstruct a typed domain event."""
    if not isinstance(payload, dict):
        raise InvalidEventEnvelopeError("Event payload must be a JSON object")

    if "contract" not in payload:
        payload = _upcast_legacy_flat_payload(payload)

    contract, metadata, data = _read_envelope(payload)
    data = _upcast_data(
        contract,
        payload["contract"]["version"],
        data,
        event_id=_optional_string(metadata.get("event_id")),
    )
    return _construct_event(contract, metadata, data)


def _upcast_legacy_flat_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Lift the pre-envelope payload without inventing business data."""
    legacy_type = payload.get("event_type")
    event_class = EVENT_TYPES.get(legacy_type) if isinstance(legacy_type, str) else None
    if event_class is None:
        raise UnsupportedEventContractError(
            f"Unknown legacy event type: {legacy_type!r}",
            event_id=_optional_string(payload.get("event_id")),
            contract_name=f"legacy.{legacy_type}" if legacy_type else "legacy.unknown",
            contract_version=0,
        )

    contract = _CONTRACT_BY_CLASS[event_class]
    metadata = {
        name: payload.get(name)
        for name in _METADATA_FIELDS
    }
    if metadata["correlation_id"] is None:
        metadata["correlation_id"] = metadata["event_id"]
    data = {
        key: value
        for key, value in payload.items()
        if key not in _METADATA_FIELDS
        and key not in {"event_type", "_legacy_delivery"}
    }
    # Flat payloads predate the namespaced registry. For contracts whose
    # domain shape changed, they are v1 even when they happen to contain all
    # additive v2 fields (the upcaster validates that case explicitly).
    legacy_version = 1
    return {
        "envelope_version": WIRE_ENVELOPE_VERSION,
        "contract": {
            "namespace": contract.namespace,
            "name": contract.name,
            "version": legacy_version,
        },
        "metadata": metadata,
        "data": data,
    }


def _read_envelope(
    payload: dict[str, Any],
) -> tuple[EventContract, dict[str, Any], dict[str, Any]]:
    unexpected_envelope_fields = set(payload) - {
        "envelope_version",
        "contract",
        "metadata",
        "data",
    }
    if unexpected_envelope_fields:
        raise InvalidEventEnvelopeError(
            "Unexpected event envelope field(s): "
            + _format_field_names(unexpected_envelope_fields)
        )

    envelope_version = payload.get("envelope_version")
    if envelope_version != WIRE_ENVELOPE_VERSION:
        raise UnsupportedEventContractError(
            f"Unsupported event envelope version: {envelope_version!r}"
        )

    raw_contract = payload.get("contract")
    metadata = payload.get("metadata")
    data = payload.get("data")
    if not isinstance(raw_contract, dict):
        raise InvalidEventEnvelopeError("Event contract must be an object")
    if not isinstance(metadata, dict):
        raise InvalidEventEnvelopeError("Event metadata must be an object")
    if not isinstance(data, dict):
        raise InvalidEventEnvelopeError("Event data must be an object")

    unexpected_contract_fields = set(raw_contract) - {"namespace", "name", "version"}
    if unexpected_contract_fields:
        raise InvalidEventEnvelopeError(
            "Unexpected event contract field(s): "
            + _format_field_names(unexpected_contract_fields),
            event_id=_optional_string(metadata.get("event_id")),
        )
    unexpected_metadata_fields = set(metadata) - _METADATA_FIELDS
    if unexpected_metadata_fields:
        raise InvalidEventEnvelopeError(
            "Unexpected event metadata field(s): "
            + _format_field_names(unexpected_metadata_fields),
            event_id=_optional_string(metadata.get("event_id")),
        )
    missing_metadata_fields = _METADATA_FIELDS - set(metadata)
    if missing_metadata_fields:
        raise InvalidEventEnvelopeError(
            "Missing event metadata field(s): "
            + _format_field_names(missing_metadata_fields),
            event_id=_optional_string(metadata.get("event_id")),
        )

    namespace = raw_contract.get("namespace")
    name = raw_contract.get("name")
    version = raw_contract.get("version")
    qualified_name = (
        f"{namespace}.{name}"
        if (
            isinstance(namespace, str)
            and isinstance(name, str)
            and len(namespace) <= 80
            and len(name) <= 64
            and re.fullmatch(r"[a-z][a-z0-9.-]*", namespace)
            and re.fullmatch(r"[a-z][a-z0-9-]*", name)
        )
        else None
    )
    event_id = _optional_string(metadata.get("event_id"))
    if qualified_name is None or not isinstance(version, int) or isinstance(version, bool):
        raise InvalidEventEnvelopeError(
            "Event contract requires string namespace/name and integer version",
            event_id=event_id,
            contract_name=qualified_name,
        )

    contract = _CONTRACT_BY_NAME.get(qualified_name)
    if contract is None or version > contract.version:
        raise UnsupportedEventContractError(
            f"Unsupported event contract {qualified_name} v{version}",
            event_id=event_id,
            contract_name=qualified_name,
            contract_version=version,
        )
    if version < 1:
        raise UnsupportedEventContractError(
            f"Invalid event contract version {qualified_name} v{version}",
            event_id=event_id,
            contract_name=qualified_name,
            contract_version=version,
        )
    return contract, metadata, data


def _upcast_data(
    contract: EventContract,
    source_version: int,
    data: dict[str, Any],
    *,
    event_id: str | None,
) -> dict[str, Any]:
    current = source_version
    result = dict(data)
    while current < contract.version:
        upcaster = _UPCASTERS.get((contract.qualified_name, current))
        if upcaster is None:
            raise UnsupportedEventContractError(
                f"No upcaster for {contract.qualified_name} v{current} -> v{current + 1}",
                event_id=event_id,
                contract_name=contract.qualified_name,
                contract_version=current,
            )
        try:
            result = upcaster(result)
        except EventContractError as error:
            if error.event_id is None:
                error.event_id = event_id
            if error.contract_name is None:
                error.contract_name = contract.qualified_name
            if error.contract_version is None:
                error.contract_version = current
            raise
        except Exception as error:
            raise InvalidEventEnvelopeError(
                f"Upcaster for {contract.qualified_name} v{current} failed: {error}",
                event_id=event_id,
                contract_name=contract.qualified_name,
                contract_version=current,
            ) from error
        if not isinstance(result, dict):
            raise InvalidEventEnvelopeError(
                f"Upcaster for {contract.qualified_name} v{current} returned non-object data",
                event_id=event_id,
                contract_name=contract.qualified_name,
                contract_version=current,
            )
        current += 1
    return result


def _construct_event(
    contract: EventContract,
    metadata: dict[str, Any],
    data: dict[str, Any],
) -> DomainEvent:
    event_id = metadata.get("event_id")
    occurred_at = metadata.get("occurred_at")
    if not isinstance(event_id, str) or not event_id.strip():
        raise InvalidEventEnvelopeError(
            "Event metadata requires a non-empty event_id",
            contract_name=contract.qualified_name,
            contract_version=contract.version,
        )
    if not isinstance(occurred_at, (str, datetime)):
        raise InvalidEventEnvelopeError(
            "Event metadata requires occurred_at",
            event_id=event_id,
            contract_name=contract.qualified_name,
            contract_version=contract.version,
        )

    for name in ("correlation_id", "causation_id"):
        value = metadata.get(name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise InvalidEventEnvelopeError(
                f"Event metadata {name} must be a non-empty string or null",
                event_id=event_id,
                contract_name=contract.qualified_name,
                contract_version=contract.version,
            )

    domain_field_names = {
        event_field.name
        for event_field in fields(contract.event_class)
        if event_field.name not in _METADATA_FIELDS
    }
    unexpected_data_fields = set(data) - domain_field_names
    if unexpected_data_fields:
        raise InvalidEventEnvelopeError(
            f"Unexpected {contract.qualified_name} data field(s): "
            + _format_field_names(unexpected_data_fields),
            event_id=event_id,
            contract_name=contract.qualified_name,
            contract_version=contract.version,
        )

    hints = get_type_hints(contract.event_class)
    kwargs: dict[str, Any] = {}
    all_values = {**data, **metadata}
    for event_field in fields(contract.event_class):
        if event_field.name not in all_values:
            continue
        value = all_values[event_field.name]
        try:
            value = _coerce_and_validate_value(
                value,
                hints.get(event_field.name),
            )
        except (TypeError, ValueError) as error:
            raise InvalidEventEnvelopeError(
                f"Invalid value for {event_field.name}: {error}",
                event_id=event_id,
                contract_name=contract.qualified_name,
                contract_version=contract.version,
            ) from error
        kwargs[event_field.name] = value

    try:
        _validate_event_semantics(contract, kwargs)
        return contract.event_class(**kwargs)
    except (TypeError, ValueError) as error:
        raise InvalidEventEnvelopeError(
            f"Invalid {contract.qualified_name} v{contract.version} data: {error}",
            event_id=event_id,
            contract_name=contract.qualified_name,
            contract_version=contract.version,
        ) from error


def _validate_event_semantics(
    contract: EventContract,
    values: dict[str, Any],
) -> None:
    """Reject deterministic business-shape poison before handler dispatch."""
    for field_name in ("book_id", "loan_id", "patron_id"):
        value = values.get(field_name)
        if value is not None and (
            not isinstance(value, str) or _REFERENCE_ID.fullmatch(value) is None
        ):
            raise ValueError(f"{field_name} must be a safe 1-64 character ID")

    reservation_id = values.get("reservation_id")
    if reservation_id is not None and (
        not isinstance(reservation_id, str)
        or _RESERVATION_UUID.fullmatch(reservation_id) is None
    ):
        raise ValueError("reservation_id must be a UUID")
    generation = values.get("reservation_generation")
    if generation is not None and (type(generation) is not int or generation < 1):
        raise ValueError("reservation_generation must be a positive integer")

    for field_name in ("borrower_email", "patron_email"):
        value = values.get(field_name)
        if value is not None and (
            not isinstance(value, str)
            or value != value.strip().lower()
            or len(value) > 254
            or _EMAIL.fullmatch(value) is None
        ):
            raise ValueError(f"{field_name} must be a normalized email address")

    borrowed_at = values.get("borrowed_at")
    for due_field in ("due_date", "return_due_date"):
        due_at = values.get(due_field)
        if borrowed_at is not None and due_at is not None and due_at <= borrowed_at:
            raise ValueError(f"{due_field} must be after borrowed_at")
    old_due_date = values.get("old_due_date")
    new_due_date = values.get("new_due_date")
    if old_due_date is not None and new_due_date is not None and new_due_date <= old_due_date:
        raise ValueError("new_due_date must be after old_due_date")

    days_overdue = values.get("days_overdue")
    if days_overdue is not None and (
        type(days_overdue) is not int or days_overdue < 1
    ):
        raise ValueError("days_overdue must be a positive integer")
    for field_name, maximum in (
        ("title", 100),
        ("book_title", 100),
        ("reason", 500),
        ("original_event_type", 64),
        ("aggregate_type", 32),
        ("aggregate_id", 64),
    ):
        value = values.get(field_name)
        if value is not None and (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > maximum
        ):
            raise ValueError(f"{field_name} must be 1-{maximum} characters")


def _encode_value(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise TypeError("Event datetimes must include an explicit UTC offset")
        value = value.astimezone(timezone.utc)
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__} in an event contract")


def _coerce_and_validate_value(
    value: Any,
    field_type: Any,
) -> Any:
    """Apply the small, explicit type system supported by event contracts."""
    origin = get_origin(field_type)
    if origin in (Union, UnionType):
        union_types = get_args(field_type)
        if value is None and type(None) in union_types:
            return None
        errors: list[Exception] = []
        for union_type in union_types:
            if union_type is type(None):
                continue
            try:
                return _coerce_and_validate_value(
                    value,
                    union_type,
                )
            except (TypeError, ValueError) as error:
                errors.append(error)
        raise TypeError(f"does not match {field_type!r}") from (
            errors[0] if errors else None
        )

    if field_type is datetime:
        if not isinstance(value, datetime):
            if not isinstance(value, str):
                raise TypeError("must be an ISO-8601 datetime")
            try:
                # Python <3.11 does not accept the otherwise standard Z suffix.
                normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
                value = datetime.fromisoformat(normalized)
            except ValueError as error:
                raise ValueError("must be an ISO-8601 datetime") from error
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("must include an explicit UTC offset")
        return value.astimezone(timezone.utc)

    if field_type is str:
        if not isinstance(value, str) or not value.strip():
            raise TypeError("must be a non-empty string")
        return value
    if field_type is bool:
        if type(value) is not bool:
            raise TypeError("must be a boolean")
        return value
    if field_type is int:
        if type(value) is not int:
            raise TypeError("must be an integer")
        return value
    if field_type is float:
        if type(value) not in (float, int):
            raise TypeError("must be a number")
        return float(value)
    if field_type in (Any, None):
        return value
    if not isinstance(value, field_type):
        raise TypeError(f"must be {getattr(field_type, '__name__', field_type)!s}")
    return value


def _optional_string(value: Any) -> str | None:
    if (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value)
    ):
        return value
    return None


def _format_field_names(values: set[Any]) -> str:
    return ", ".join(sorted(str(value) for value in values))

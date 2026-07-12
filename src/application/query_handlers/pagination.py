"""Bounded offset pagination and backend-neutral keyset cursors."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Mapping, Sequence, TypeVar

from src.application.exceptions import ApplicationException


MAX_PAGE_SIZE = 1_000
MAX_RESULT_WINDOW = 10_000
MAX_CURSOR_LENGTH = 1_024

T = TypeVar("T")


class InvalidPaginationError(ApplicationException, ValueError):
    """Raised before an invalid page can reach a backend or circuit breaker."""


@dataclass(frozen=True)
class QueryPage(Generic[T]):
    """One deterministic page plus an opaque cursor for the next page."""

    items: list[T]
    next_cursor: str | None
    total: int | None = None


def validate_pagination(
    *, limit: int, offset: int = 0, cursor: str | None = None
) -> None:
    """Validate pagination at the application boundary.

    Offset pagination is bounded by the Elasticsearch result window. Cursors
    are the stable option for large or changing result sets.
    """
    if isinstance(limit, bool) or limit < 1 or limit > MAX_PAGE_SIZE:
        raise InvalidPaginationError(
            f"limit must be between 1 and {MAX_PAGE_SIZE}"
        )
    if isinstance(offset, bool) or offset < 0:
        raise InvalidPaginationError("offset must be non-negative")
    if cursor is not None and offset:
        raise InvalidPaginationError("cursor and non-zero offset are mutually exclusive")
    if cursor is not None and (not cursor or len(cursor) > MAX_CURSOR_LENGTH):
        raise InvalidPaginationError("invalid cursor")
    if cursor is None and offset + limit > MAX_RESULT_WINDOW:
        raise InvalidPaginationError(
            f"offset + limit must not exceed {MAX_RESULT_WINDOW}; use a cursor"
        )


def cursor_scope(name: str, filters: Mapping[str, Any]) -> str:
    """Fingerprint the query shape so cursors cannot cross filter sets."""
    canonical = json.dumps(
        {"name": name, "filters": filters},
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


CURSOR_BACKENDS = frozenset({"elasticsearch", "postgresql"})


def encode_cursor(
    scope: str,
    sort_values: Sequence[Any],
    *,
    backend: str | None = None,
) -> str:
    if backend is not None and backend not in CURSOR_BACKENDS:
        raise ValueError("unsupported cursor backend")
    envelope: dict[str, Any] = {
        "v": 1,
        "scope": scope,
        "sort": list(sort_values),
    }
    if backend is not None:
        envelope["backend"] = backend
    payload = json.dumps(
        envelope,
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(
    cursor: str, *, expected_scope: str, expected_values: int
) -> list[Any]:
    values, _backend = decode_cursor_with_backend(
        cursor,
        expected_scope=expected_scope,
        expected_values=expected_values,
    )
    return values


def decode_cursor_with_backend(
    cursor: str,
    *,
    expected_scope: str,
    expected_values: int,
) -> tuple[list[Any], str | None]:
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidPaginationError("invalid cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidPaginationError("invalid cursor") from exc

    if (
        not isinstance(payload, dict)
        or set(payload) - {"v", "scope", "sort", "backend"}
        or payload.get("v") != 1
        or payload.get("scope") != expected_scope
        or not isinstance(payload.get("sort"), list)
        or len(payload["sort"]) != expected_values
    ):
        raise InvalidPaginationError("cursor does not match this query")
    backend = payload.get("backend")
    if backend is not None and backend not in CURSOR_BACKENDS:
        raise InvalidPaginationError("cursor has an unsupported backend")
    return payload["sort"], backend


def cursor_string(
    value: Any,
    *,
    field: str,
    max_length: int,
    pattern: str | None = None,
) -> str:
    """Validate a decoded sort value before it can reach a backend."""
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise InvalidPaginationError(f"cursor contains an invalid {field}")
    if pattern is not None and re.fullmatch(pattern, value) is None:
        raise InvalidPaginationError(f"cursor contains an invalid {field}")
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported cursor value: {type(value).__name__}")

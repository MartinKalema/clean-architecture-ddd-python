"""Durable HTTP command-idempotency contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping, Protocol

from src.application.exceptions import (
    IdempotencyKeyConflictException,
    InvalidIdempotencyKeyException,
)


@dataclass(frozen=True)
class IdempotencyKey:
    """Bounded, log-safe opaque identity supplied in an HTTP header."""

    value: str

    def __post_init__(self) -> None:
        value = str(self.value).strip()
        if not 8 <= len(value) <= 128 or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]*", value
        ):
            raise InvalidIdempotencyKeyException()
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class CommandReceipt:
    """Committed response for one command scope and idempotency key."""

    scope: str
    idempotency_key: str
    request_hash: str
    response: Mapping[str, Any]
    created_at: datetime | None = None


class ICommandReceiptRepository(Protocol):
    async def get(self, scope: str, idempotency_key: str) -> CommandReceipt | None:
        ...

    async def add(self, receipt: CommandReceipt) -> None:
        ...


def command_fingerprint(values: Mapping[str, Any]) -> str:
    """Hash canonical command facts without storing request PII in the key."""
    payload = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_value,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_matching_receipt(
    receipt: CommandReceipt,
    request_hash: str,
) -> Mapping[str, Any]:
    if receipt.request_hash != request_hash:
        raise IdempotencyKeyConflictException(receipt.idempotency_key)
    return receipt.response


def _json_value(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported command fingerprint value: {type(value).__name__}")

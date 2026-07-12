"""Committed Patron aggregate snapshots returned by command handlers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping, TypeVar

if TYPE_CHECKING:
    from src.domain.patron import Patron

_Snapshot = TypeVar("_Snapshot", bound="PatronSnapshot")


@dataclass(frozen=True)
class PatronSnapshot:
    """Transport-neutral state from the committed write model."""

    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    membership_tier: str
    is_suspended: bool
    suspended_reason: str | None
    registered_at: datetime

    @classmethod
    def from_patron(cls: type[_Snapshot], patron: Patron) -> _Snapshot:
        return cls(
            id=patron.id.value,
            name=patron.name.full_name,
            first_name=patron.name.first_name,
            last_name=patron.name.last_name,
            email=patron.email.value,
            membership_tier=patron.membership_tier.value,
            is_suspended=patron.is_suspended,
            suspended_reason=patron.suspended_reason,
            registered_at=patron.registered_at,
        )

    @classmethod
    def from_mapping(
        cls: type[_Snapshot], values: Mapping[str, Any]
    ) -> _Snapshot:
        payload = dict(values)
        registered_at = payload.get("registered_at")
        if isinstance(registered_at, str):
            payload["registered_at"] = datetime.fromisoformat(registered_at)
        return cls(**payload)

"""
Read models - the query side's output DTOs.

These are denormalized views optimized for display, separate from the
write model (the domain aggregates). They are the data structures that
cross the boundary out of the application layer, so they are defined
once here and shared by the query handlers, the query-repository ports,
and their infrastructure implementations.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class BookReadModel:
    """Read model for Book."""
    id: str
    title: str
    author: str
    is_borrowed: bool
    status: str = "available"
    borrowed_at: Optional[datetime] = None
    return_due_date: Optional[datetime] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BookReadModel":
        """Hydrate from Elasticsearch or a JSON cache without leaking strings."""
        status = str(value.get("status", "available"))
        return cls(
            id=str(value["id"]),
            title=str(value.get("title", "")),
            author=str(value.get("author", "")),
            is_borrowed=status == "borrowed",
            status=status,
            borrowed_at=_optional_datetime(value.get("borrowed_at"), "borrowed_at"),
            return_due_date=_optional_datetime(
                value.get("return_due_date"), "return_due_date"
            ),
        )


@dataclass(frozen=True)
class PatronReadModel:
    """Read model for Patron."""
    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    membership_tier: str
    is_suspended: bool
    suspended_reason: Optional[str]
    registered_at: datetime

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PatronReadModel":
        return cls(
            id=str(value["id"]),
            name=str(value.get("name", value.get("full_name", ""))),
            first_name=str(value.get("first_name", "")),
            last_name=str(value.get("last_name", "")),
            email=str(value.get("email", "")),
            membership_tier=str(value.get("membership_tier", "regular")),
            is_suspended=bool(value.get("is_suspended", False)),
            suspended_reason=value.get("suspended_reason"),
            registered_at=_required_datetime(
                value.get("registered_at"), "registered_at"
            ),
        )


@dataclass(frozen=True)
class LoanReadModel:
    """Read model for Loan."""
    id: str
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime]
    status: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LoanReadModel":
        return cls(
            id=str(value["id"]),
            patron_id=str(value.get("patron_id", "")),
            patron_email=str(value.get("patron_email", "")),
            catalog_book_id=str(value.get("catalog_book_id", "")),
            book_title=str(value.get("book_title", "")),
            borrowed_at=_required_datetime(value.get("borrowed_at"), "borrowed_at"),
            due_date=_required_datetime(value.get("due_date"), "due_date"),
            returned_at=_optional_datetime(value.get("returned_at"), "returned_at"),
            status=str(value.get("status", "")),
        )


def _required_datetime(value: Any, field: str) -> datetime:
    result = _optional_datetime(value, field)
    if result is None:
        raise ValueError(f"{field} must be a datetime")
    return result


def _optional_datetime(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} is not an ISO-8601 datetime") from exc
    raise ValueError(f"{field} must be a datetime or ISO-8601 string")

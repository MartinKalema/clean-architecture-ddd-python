"""Domain-safe time normalization."""

from datetime import datetime, timezone

from .exceptions import ValidationException


def require_utc_datetime(value: datetime, field_name: str) -> datetime:
    """Reject ambiguous local time and normalize aware values to UTC."""
    if not isinstance(value, datetime):
        raise ValidationException(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationException(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc)

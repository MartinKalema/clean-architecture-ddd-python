"""
Value Objects for the Catalog bounded context.
"""
import uuid
from dataclasses import dataclass

from src.domain.shared_kernel.exceptions import ValidationException


@dataclass(frozen=True)
class BookId:
    """Unique identifier for a book in the catalog."""
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValidationException("BookId cannot be empty")

    @classmethod
    def next_id(cls) -> "BookId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class Title:
    """The title of a book."""
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValidationException("Title cannot be empty")
        if len(self.value) > 100:
            raise ValidationException("Title cannot be longer than 100 characters")


@dataclass(frozen=True)
class Author:
    """The author of a book."""
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValidationException("Author cannot be empty")


@dataclass(frozen=True)
class ISBN:
    """International Standard Book Number (optional)."""
    value: str

    def __post_init__(self):
        if self.value:
            clean = self.value.replace("-", "")
            if len(clean) not in (10, 13):
                raise ValidationException("ISBN must be 10 or 13 digits")
            if not clean.isdigit():
                raise ValidationException("ISBN must contain only digits")

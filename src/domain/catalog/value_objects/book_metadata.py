"""
Value Objects for the Catalog bounded context.

These represent immutable concepts in the catalog domain that are defined
by their attributes rather than identity.
"""
from dataclasses import dataclass
import uuid


@dataclass(frozen=True)
class CatalogBookId:
    """
    Unique identifier for a book in the catalog.

    This ID is shared with the Lending context as part of the
    Published Language between contexts.
    """

    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("CatalogBookId cannot be empty")

    @classmethod
    def next_id(cls) -> "CatalogBookId":
        return cls(str(uuid.uuid4()))


@dataclass(frozen=True)
class Title:
    """The title of a book."""

    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("Title cannot be empty")
        if len(self.value) > 200:
            raise ValueError("Title cannot exceed 200 characters")


@dataclass(frozen=True)
class Author:
    """The author of a book."""

    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("Author cannot be empty")


@dataclass(frozen=True)
class ISBN:
    """
    International Standard Book Number.

    Optional in catalog as not all books have ISBN.
    """

    value: str

    def __post_init__(self):
        if self.value:
            # Remove hyphens for validation
            clean = self.value.replace("-", "")
            if len(clean) not in (10, 13):
                raise ValueError("ISBN must be 10 or 13 digits")
            if not clean.isdigit():
                raise ValueError("ISBN must contain only digits")

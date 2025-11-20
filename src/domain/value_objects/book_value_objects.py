from dataclasses import dataclass
import uuid
from src.domain.exceptions.book_exceptions import ValidationException

@dataclass(frozen=True)
class BookId:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValidationException("BookId cannot be empty")

    @classmethod
    def next_id(cls) -> 'BookId':
        return cls(str(uuid.uuid4()))

@dataclass(frozen=True)
class Title:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValidationException("Title cannot be empty")
        if len(self.value) > 100:
            raise ValidationException("Title cannot be longer than 100 characters")

@dataclass(frozen=True)
class Author:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValidationException("Author cannot be empty")

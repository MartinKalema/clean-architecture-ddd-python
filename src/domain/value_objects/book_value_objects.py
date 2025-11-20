from dataclasses import dataclass
import uuid

@dataclass(frozen=True)
class BookId:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("BookId cannot be empty")

    @classmethod
    def next_id(cls) -> 'BookId':
        return cls(str(uuid.uuid4()))

@dataclass(frozen=True)
class Title:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("Title cannot be empty")
        if len(self.value) > 100:
            raise ValueError("Title cannot be longer than 100 characters")

@dataclass(frozen=True)
class Author:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("Author cannot be empty")

from typing import Protocol
from src.domain.interfaces.book_repository import BookRepository

class UnitOfWork(Protocol):
    books: BookRepository

    async def __aenter__(self) -> "UnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    async def commit(self):
        ...

    async def rollback(self):
        ...

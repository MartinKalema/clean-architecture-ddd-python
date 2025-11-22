from abc import ABC, abstractmethod
from typing import Optional
from src.domain.interfaces.book_repository import BookRepository

class UnitOfWork(ABC):
    books: BookRepository

    @abstractmethod
    async def __aenter__(self) -> "UnitOfWork":
        ...

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    @abstractmethod
    async def commit(self):
        ...

    @abstractmethod
    async def rollback(self):
        ...

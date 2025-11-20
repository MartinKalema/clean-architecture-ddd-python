from abc import ABC, abstractmethod
from typing import List, Optional
from src.domain.entities.book import Book

class BookRepository(ABC):
    @abstractmethod
    async def add(self, book: Book) -> Book:
        pass

    @abstractmethod
    async def get_all(self) -> List[Book]:
        pass

    @abstractmethod
    async def get_by_id(self, book_id: str) -> Optional[Book]:
        pass

    @abstractmethod
    async def update(self, book: Book) -> None:
        pass

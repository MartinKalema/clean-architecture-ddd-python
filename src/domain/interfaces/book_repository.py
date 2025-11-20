from typing import List, Optional, Protocol
from src.domain.entities.book import Book

class BookRepository(Protocol):
    async def add(self, book: Book) -> Book:
        ...

    async def get_all(self) -> List[Book]:
        ...

    async def get_by_id(self, book_id: str) -> Optional[Book]:
        ...

    async def update(self, book: Book) -> None:
        ...

from typing import Optional

from src.domain.catalog.interfaces.book_query_repository import BookQueryRepository
from src.domain.lending.interfaces.catalog_service import BookReference


class CatalogServiceAdapter:
    """
    Implementation of the CatalogService interface.

    Bridges Lending context to Catalog context.
    """

    def __init__(self, book_repository: BookQueryRepository):
        self.book_repository = book_repository

    async def get_book_reference(self, catalog_book_id: str) -> Optional[BookReference]:
        book = await self.book_repository.get_by_id(catalog_book_id)
        if not book:
            return None
        
        return BookReference(
            catalog_book_id=book.id,
            title=book.title,
            author=book.author
        )

    async def book_exists(self, catalog_book_id: str) -> bool:
        book = await self.book_repository.get_by_id(catalog_book_id)
        return book is not None

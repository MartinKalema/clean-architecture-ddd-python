"""
CatalogBook Aggregate Root for the Catalog bounded context.

In this context, a Book is purely a bibliographic record - metadata about
a published work. It does NOT track:
- Whether the book is borrowed (that's Lending's responsibility)
- Who has it (that's Lending's responsibility)
- Due dates (that's Lending's responsibility)

This separation follows DDD's bounded context principle - each context
has its own model of "Book" optimized for its specific needs.
"""
from dataclasses import dataclass, field
from typing import Optional

from src.domain.shared_kernel import AggregateRoot
from src.domain.catalog.value_objects import CatalogBookId, Title, Author, ISBN
from src.domain.catalog.events.catalog_events import BookAddedToCatalog


@dataclass
class CatalogBook(AggregateRoot):
    """
    A bibliographic record in the library catalog.

    This is the Catalog context's view of a book - purely metadata.
    The Lending context has its own model (LoanableBook) that references
    this via CatalogBookId.
    """

    title: Title
    author: Author
    id: CatalogBookId = field(default_factory=CatalogBookId.next_id)
    isbn: Optional[ISBN] = None
    description: Optional[str] = None

    def __post_init__(self):
        # Raise event when book is created
        self.add_event(
            BookAddedToCatalog(
                book_id=self.id.value,
                title=self.title.value,
                author=self.author.value,
            )
        )

    def update_description(self, description: str) -> None:
        """Update the book's description."""
        self.description = description

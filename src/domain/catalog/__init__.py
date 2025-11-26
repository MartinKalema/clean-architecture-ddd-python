"""
Catalog Bounded Context

This context is responsible for managing the library's book catalog - the
bibliographic records of all books in the library. It handles:

- Book metadata (title, author, ISBN, description)
- Adding new books to the catalog
- Updating book information
- Categorization and tagging

Key Aggregates:
- CatalogBook: The bibliographic record of a book

Ubiquitous Language:
- CatalogBook: A bibliographic record describing a book's metadata
- Title: The name of the book
- Author: The person who wrote the book
- ISBN: International Standard Book Number

Context Relationships:
- Upstream to Lending: Provides book identity (CatalogBookId) that Lending references
- Relationship Type: Open Host Service with Published Language (events)
"""
from .entities.catalog_book import CatalogBook
from .value_objects.book_metadata import CatalogBookId, Title, Author, ISBN
from .events.catalog_events import BookAddedToCatalog

__all__ = [
    "CatalogBook",
    "CatalogBookId",
    "Title",
    "Author",
    "ISBN",
    "BookAddedToCatalog",
]

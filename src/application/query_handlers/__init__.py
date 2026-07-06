"""
Query handlers for read operations (CQRS - Query side).

Queries read from optimized read models and never modify state.
"""
from .get_book import GetBookHandler, GetBookQuery
from .interfaces import (
    IBookQueryRepository,
    ILoanQueryRepository,
    IPatronQueryRepository,
)
from .list_books import ListBooksHandler, ListBooksQuery
from .read_models import BookReadModel, LoanReadModel, PatronReadModel

__all__ = [
    "ListBooksQuery",
    "ListBooksHandler",
    "GetBookQuery",
    "GetBookHandler",
    "BookReadModel",
    "PatronReadModel",
    "LoanReadModel",
    "IBookQueryRepository",
    "IPatronQueryRepository",
    "ILoanQueryRepository",
]

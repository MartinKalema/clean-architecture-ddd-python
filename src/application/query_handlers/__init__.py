"""
Query handlers for read operations (CQRS - Query side).

Queries read from optimized read models and never modify state.
"""
from .get_book import GetBookHandler, GetBookQuery
from .get_borrow_operation import (
    BorrowOperationResult,
    GetBorrowOperationHandler,
    GetBorrowOperationQuery,
)
from .interfaces import (
    IBookQueryRepository,
    ILoanQueryRepository,
    IPatronQueryRepository,
)
from .list_books import ListBooksHandler, ListBooksQuery
from .pagination import (
    InvalidPaginationError,
    QueryPage,
    decode_cursor_with_backend,
)
from .read_models import BookReadModel, LoanReadModel, PatronReadModel

__all__ = [
    "ListBooksQuery",
    "ListBooksHandler",
    "GetBookQuery",
    "GetBookHandler",
    "GetBorrowOperationQuery",
    "GetBorrowOperationHandler",
    "BorrowOperationResult",
    "BookReadModel",
    "PatronReadModel",
    "LoanReadModel",
    "QueryPage",
    "InvalidPaginationError",
    "decode_cursor_with_backend",
    "IBookQueryRepository",
    "IPatronQueryRepository",
    "ILoanQueryRepository",
]

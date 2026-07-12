from typing import Annotated, List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, Query, Response

from src.application.command_handlers import (
    AddBookCommand,
    AddBookHandler,
    BorrowBookCommand,
    BorrowBookHandler,
)
from src.application.query_handlers import (
    GetBookHandler,
    GetBookQuery,
    GetBorrowOperationHandler,
    GetBorrowOperationQuery,
    ListBooksHandler,
    ListBooksQuery,
)
from src.container import Container
from src.presentation.api.pagination import set_page_headers
from src.presentation.api.models.book_models import (
    BookCreate,
    BookResponse,
    BorrowBookResponse,
    BorrowOperationResponse,
    BorrowRequest,
)

router = APIRouter()


@router.post("/books", response_model=BookResponse, status_code=201)
@inject
async def create_book(
    book: BookCreate,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    handler: AddBookHandler = Depends(Provide[Container.add_book_handler])
):
    """Create a new book (Command)."""
    command = AddBookCommand(
        title=book.title,
        author=book.author,
        idempotency_key=idempotency_key,
    )
    result = await handler.handle(command)
    return BookResponse(
        id=result.id,
        title=result.title,
        author=result.author,
        is_borrowed=result.is_borrowed,
        status=result.status,
    )


@router.post(
    "/books/{book_id}/borrow",
    response_model=BorrowBookResponse,
    status_code=202,
)
@inject
async def borrow_book(
    book_id: str,
    borrow_request: BorrowRequest,
    response: Response,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    handler: BorrowBookHandler = Depends(Provide[Container.borrow_book_handler])
):
    """Borrow a book (Command)."""
    command = BorrowBookCommand(
        book_id=book_id,
        borrower_email=borrow_request.borrower_email,
        idempotency_key=idempotency_key,
    )
    result = await handler.handle(command)
    response.headers["Location"] = f"/borrow-operations/{result.operation_id}"
    return BorrowBookResponse(
        id=result.id,
        title=result.title,
        author=result.author,
        is_borrowed=result.is_borrowed,
        status=result.status,
        reservation_id=result.reservation_id,
        reservation_generation=result.reservation_generation,
        operation_id=result.operation_id,
        return_due_date=result.return_due_date,
    )


@router.get(
    "/borrow-operations/{operation_id}",
    response_model=BorrowOperationResponse,
)
@inject
async def get_borrow_operation(
    operation_id: str,
    handler: GetBorrowOperationHandler = Depends(
        Provide[Container.get_borrow_operation_handler]
    ),
):
    """Poll the durable outcome of an accepted borrow workflow."""
    result = await handler.handle(GetBorrowOperationQuery(operation_id))
    return BorrowOperationResponse(**result.__dict__)


@router.get("/books", response_model=List[BookResponse])
@inject
async def list_books(
    response: Response,
    only_available: bool = Query(False, description="Filter to only available books"),
    only_borrowed: bool = Query(False, description="Filter to only borrowed books"),
    author: Optional[str] = Query(
        None, max_length=200, description="Filter by author name (partial match)"
    ),
    title: Optional[str] = Query(
        None, max_length=100, description="Filter by title (partial match)"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    cursor: Optional[str] = Query(
        None,
        max_length=1024,
        description="Opaque continuation cursor; cannot be combined with non-zero offset",
    ),
    handler: ListBooksHandler = Depends(Provide[Container.list_books_handler])
):
    """List books with optional filtering (Query)."""
    query = ListBooksQuery(
        only_available=only_available,
        only_borrowed=only_borrowed,
        author_contains=author,
        title_contains=title,
        limit=limit,
        offset=offset,
        cursor=cursor,
    )
    page = await handler.handle_page(query)
    set_page_headers(
        response,
        next_cursor=page.next_cursor,
        total=page.total,
    )
    return [
        BookResponse(
            id=book.id,
            title=book.title,
            author=book.author,
            is_borrowed=book.is_borrowed,
            status=book.status
        )
        for book in page.items
    ]


@router.get("/books/{book_id}", response_model=BookResponse)
@inject
async def get_book(
    book_id: str,
    handler: GetBookHandler = Depends(Provide[Container.get_book_handler])
):
    """Get a single book by ID (Query)."""
    query = GetBookQuery(book_id=book_id)
    result = await handler.handle(query)
    return BookResponse(
        id=result.id,
        title=result.title,
        author=result.author,
        is_borrowed=result.is_borrowed,
        status=result.status,
    )

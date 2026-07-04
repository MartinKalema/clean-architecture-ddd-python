from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.command_handlers import (
    AddBookCommand,
    AddBookHandler,
    BorrowBookCommand,
    BorrowBookHandler,
    ReturnBookCommand,
    ReturnBookHandler,
)
from src.application.query_handlers import (
    GetBookHandler,
    GetBookQuery,
    ListBooksHandler,
    ListBooksQuery,
)
from src.container import Container
from src.domain.catalog import DomainException
from src.presentation.api.models.book_models import (
    BookCreate,
    BookResponse,
    BorrowRequest,
)

router = APIRouter()


@router.post("/books", response_model=BookResponse)
@inject
async def create_book(
    book: BookCreate,
    handler: AddBookHandler = Depends(Provide[Container.add_book_handler])
):
    """Create a new book (Command)."""
    try:
        command = AddBookCommand(title=book.title, author=book.author)
        result = await handler.handle(command)
        return BookResponse(
            id=result.id,
            title=result.title,
            author=result.author,
            is_borrowed=result.is_borrowed,
            status=result.status
        )
    except DomainException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/books/{book_id}/borrow", response_model=BookResponse)
@inject
async def borrow_book(
    book_id: str,
    borrow_request: BorrowRequest,
    handler: BorrowBookHandler = Depends(Provide[Container.borrow_book_handler])
):
    """Borrow a book (Command)."""
    try:
        command = BorrowBookCommand(
            book_id=book_id,
            borrower_email=borrow_request.borrower_email
        )
        result = await handler.handle(command)
        return BookResponse(
            id=result.id,
            title=result.title,
            author=result.author,
            is_borrowed=result.is_borrowed,
            status=result.status
        )
    except DomainException as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/books/{book_id}/return", response_model=BookResponse)
@inject
async def return_book(
    book_id: str,
    handler: ReturnBookHandler = Depends(Provide[Container.return_book_handler])
):
    """Return a borrowed book (Command)."""
    try:
        command = ReturnBookCommand(book_id=book_id)
        result = await handler.handle(command)
        return BookResponse(
            id=result.id,
            title=result.title,
            author=result.author,
            is_borrowed=result.is_borrowed,
            status=result.status
        )
    except DomainException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/books", response_model=List[BookResponse])
@inject
async def list_books(
    only_available: bool = Query(False, description="Filter to only available books"),
    only_borrowed: bool = Query(False, description="Filter to only borrowed books"),
    author: Optional[str] = Query(None, description="Filter by author name (partial match)"),
    title: Optional[str] = Query(None, description="Filter by title (partial match)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
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
    )
    results = await handler.handle(query)
    return [
        BookResponse(
            id=book.id,
            title=book.title,
            author=book.author,
            is_borrowed=book.is_borrowed,
            status=book.status
        )
        for book in results
    ]


@router.get("/books/{book_id}", response_model=BookResponse)
@inject
async def get_book(
    book_id: str,
    handler: GetBookHandler = Depends(Provide[Container.get_book_handler])
):
    """Get a single book by ID (Query)."""
    try:
        query = GetBookQuery(book_id=book_id)
        result = await handler.handle(query)
        return BookResponse(
            id=result.id,
            title=result.title,
            author=result.author,
            is_borrowed=result.is_borrowed,
            status=result.status
        )
    except DomainException as e:
        raise HTTPException(status_code=404, detail=str(e))

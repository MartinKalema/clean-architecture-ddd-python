from fastapi import APIRouter, Depends, HTTPException
from typing import List
from dependency_injector.wiring import inject, Provide

from src.presentation.api.models.book_models import BookCreate, BookResponse, BorrowRequest
from src.container import Container
from src.application.use_cases.add_book import AddBook
from src.application.use_cases.list_books import ListBooks
from src.application.use_cases.borrow_book import BorrowBook
from src.application.use_cases.return_book import ReturnBook
from src.application.use_cases.get_book import GetBook
from src.application.dto.book_dto import AddBookInputDto, BorrowBookInputDto, ReturnBookInputDto, GetBookInputDto
from src.domain.catalog import DomainException

router = APIRouter()


@router.post("/books", response_model=BookResponse)
@inject
async def create_book(
    book: BookCreate,
    use_case: AddBook = Depends(Provide[Container.add_book_use_case])
):
    try:
        input_dto = AddBookInputDto(title=book.title, author=book.author)
        output_dto = await use_case.execute(input_dto)
        return BookResponse(
            id=output_dto.id,
            title=output_dto.title,
            author=output_dto.author,
            is_borrowed=output_dto.is_borrowed
        )
    except DomainException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/books", response_model=List[BookResponse])
@inject
async def list_books(
    use_case: ListBooks = Depends(Provide[Container.list_books_use_case])
):
    output_dtos = await use_case.execute()
    return [
        BookResponse(
            id=dto.id,
            title=dto.title,
            author=dto.author,
            is_borrowed=dto.is_borrowed
        )
        for dto in output_dtos
    ]


@router.get("/books/{book_id}", response_model=BookResponse)
@inject
async def get_book(
    book_id: str,
    use_case: GetBook = Depends(Provide[Container.get_book_use_case])
):
    try:
        input_dto = GetBookInputDto(book_id=book_id)
        output_dto = await use_case.execute(input_dto)
        return BookResponse(
            id=output_dto.id,
            title=output_dto.title,
            author=output_dto.author,
            is_borrowed=output_dto.is_borrowed
        )
    except DomainException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/books/{book_id}/borrow", response_model=BookResponse)
@inject
async def borrow_book(
    book_id: str,
    borrow_request: BorrowRequest,
    use_case: BorrowBook = Depends(Provide[Container.borrow_book_use_case])
):
    input_dto = BorrowBookInputDto(
        book_id=book_id,
        borrower_email=borrow_request.borrower_email
    )
    output_dto = await use_case.execute(input_dto)
    return BookResponse(
        id=output_dto.id,
        title=output_dto.title,
        author=output_dto.author,
        is_borrowed=output_dto.is_borrowed
    )


@router.post("/books/{book_id}/return", response_model=BookResponse)
@inject
async def return_book(
    book_id: str,
    use_case: ReturnBook = Depends(Provide[Container.return_book_use_case])
):
    input_dto = ReturnBookInputDto(book_id=book_id)
    output_dto = await use_case.execute(input_dto)
    return BookResponse(
        id=output_dto.id,
        title=output_dto.title,
        author=output_dto.author,
        is_borrowed=output_dto.is_borrowed
    )

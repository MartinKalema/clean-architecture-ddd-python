"""
Loan API Routes.
"""
from datetime import datetime
from typing import Annotated, List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field

from src.application.command_handlers.extend_loan import (
    ExtendLoanCommand,
    ExtendLoanResult,
)
from src.application.command_handlers.return_loan import (
    ReturnLoanCommand,
    ReturnLoanResult,
)
from src.application.ports import ICommandHandler
from src.application.query_handlers.get_loan import (
    GetLoanHandler,
    GetLoanQuery,
)
from src.application.query_handlers.list_patron_loans import (
    ListPatronLoansHandler,
    ListPatronLoansQuery,
)
from src.container import Container
from src.presentation.api.pagination import set_page_headers

router = APIRouter(prefix="/loans", tags=["Loans"])


class ExtendLoanRequest(BaseModel):
    """Request model for extending a loan."""
    days: int = Field(default=7, ge=1, le=365)


class LoanResponse(BaseModel):
    """Response model for loan."""
    id: str
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime] = None
    status: str


class ExtendLoanResponse(BaseModel):
    """Response model for extended loan."""
    id: str
    new_due_date: datetime


class ReturnLoanResponse(BaseModel):
    """Response model for returned loan."""
    id: str
    returned_at: datetime
    was_overdue: bool


@router.get("/patron/{patron_id}", response_model=List[LoanResponse])
@inject
async def list_patron_loans(
    patron_id: str,
    response: Response,
    only_active: bool = Query(False),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    cursor: Optional[str] = Query(None, max_length=1024),
    handler: ListPatronLoansHandler = Depends(Provide[Container.list_patron_loans_handler]),
):
    """List loans for a patron."""
    query = ListPatronLoansQuery(
        patron_id=patron_id,
        only_active=only_active,
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
        LoanResponse(
            id=loan.id,
            patron_id=loan.patron_id,
            patron_email=loan.patron_email,
            catalog_book_id=loan.catalog_book_id,
            book_title=loan.book_title,
            borrowed_at=loan.borrowed_at,
            due_date=loan.due_date,
            returned_at=loan.returned_at,
            status=loan.status,
        )
        for loan in page.items
    ]


@router.get("/{loan_id}", response_model=LoanResponse)
@inject
async def get_loan(
    loan_id: str,
    handler: GetLoanHandler = Depends(Provide[Container.get_loan_handler]),
):
    """Get a loan by ID."""
    query = GetLoanQuery(loan_id=loan_id)
    result = await handler.handle(query)
    return LoanResponse(
        id=result.id,
        patron_id=result.patron_id,
        patron_email=result.patron_email,
        catalog_book_id=result.catalog_book_id,
        book_title=result.book_title,
        borrowed_at=result.borrowed_at,
        due_date=result.due_date,
        returned_at=result.returned_at,
        status=result.status,
    )


@router.post("/{loan_id}/extend", response_model=ExtendLoanResponse)
@inject
async def extend_loan(
    loan_id: str,
    request: ExtendLoanRequest,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    operation: ICommandHandler[ExtendLoanCommand, ExtendLoanResult] = Depends(
        Provide[Container.extend_loan]
    ),
):
    """Extend a loan."""
    command = ExtendLoanCommand(
        loan_id=loan_id,
        days=request.days,
        idempotency_key=idempotency_key,
    )
    result = await operation.handle(command)
    return ExtendLoanResponse(
        id=result.id,
        new_due_date=result.new_due_date,
    )


@router.post("/{loan_id}/return", response_model=ReturnLoanResponse)
@inject
async def return_loan(
    loan_id: str,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    operation: ICommandHandler[ReturnLoanCommand, ReturnLoanResult] = Depends(
        Provide[Container.return_loan]
    ),
):
    """Return a loan."""
    command = ReturnLoanCommand(
        loan_id=loan_id,
        idempotency_key=idempotency_key,
    )
    result = await operation.handle(command)
    return ReturnLoanResponse(
        id=result.id,
        returned_at=result.returned_at,
        was_overdue=result.was_overdue,
    )

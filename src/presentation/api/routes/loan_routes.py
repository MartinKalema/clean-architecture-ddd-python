"""
Loan API Routes.
"""
from datetime import datetime
from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from src.application.command_handlers.create_loan import (
    CreateLoanCommand,
    CreateLoanHandler,
)
from src.application.command_handlers.extend_loan import (
    ExtendLoanCommand,
    ExtendLoanHandler,
)
from src.application.command_handlers.return_loan import (
    ReturnLoanCommand,
    ReturnLoanHandler,
)
from src.application.query_handlers.get_loan import (
    GetLoanHandler,
    GetLoanQuery,
)
from src.application.query_handlers.list_patron_loans import (
    ListPatronLoansHandler,
    ListPatronLoansQuery,
)
from src.container import Container
from src.domain.lending.exceptions import (
    BookNotAvailableException,
    CannotExtendOverdueLoanException,
    LendingException,
    LoanAlreadyReturnedException,
    LoanNotFoundException,
)

router = APIRouter(prefix="/loans", tags=["Loans"])


class LoanCreate(BaseModel):
    """Request model for creating a loan."""
    patron_id: str
    patron_email: str
    catalog_book_id: str
    book_title: str
    loan_duration_days: int = 14


class ExtendLoanRequest(BaseModel):
    """Request model for extending a loan."""
    days: int = 7


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


@router.post("", response_model=LoanResponse, status_code=201)
@inject
async def create_loan(
    loan: LoanCreate,
    handler: CreateLoanHandler = Depends(Provide[Container.create_loan_handler]),
):
    """Create a new loan."""
    try:
        command = CreateLoanCommand(
            patron_id=loan.patron_id,
            patron_email=loan.patron_email,
            catalog_book_id=loan.catalog_book_id,
            book_title=loan.book_title,
            loan_duration_days=loan.loan_duration_days,
        )
        result = await handler.handle(command)
        return LoanResponse(
            id=result.id,
            patron_id=result.patron_id,
            patron_email=loan.patron_email,
            catalog_book_id=result.catalog_book_id,
            book_title=result.book_title,
            borrowed_at=result.borrowed_at,
            due_date=result.due_date,
            status="active",
        )
    except BookNotAvailableException as e:
        raise HTTPException(status_code=409, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"Book {loan.catalog_book_id} is no longer available")
    except LendingException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/patron/{patron_id}", response_model=List[LoanResponse])
@inject
async def list_patron_loans(
    patron_id: str,
    only_active: bool = Query(False),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    handler: ListPatronLoansHandler = Depends(Provide[Container.list_patron_loans_handler]),
):
    """List loans for a patron."""
    query = ListPatronLoansQuery(
        patron_id=patron_id,
        only_active=only_active,
        limit=limit,
        offset=offset,
    )
    results = await handler.handle(query)
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
        for loan in results
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
    if not result:
        raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")
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
    handler: ExtendLoanHandler = Depends(Provide[Container.extend_loan_handler]),
):
    """Extend a loan."""
    try:
        command = ExtendLoanCommand(loan_id=loan_id, days=request.days)
        result = await handler.handle(command)
        return ExtendLoanResponse(
            id=result.id,
            new_due_date=result.new_due_date,
        )
    except LoanNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CannotExtendOverdueLoanException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LendingException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{loan_id}/return", response_model=ReturnLoanResponse)
@inject
async def return_loan(
    loan_id: str,
    handler: ReturnLoanHandler = Depends(Provide[Container.return_loan_handler]),
):
    """Return a loan."""
    try:
        command = ReturnLoanCommand(loan_id=loan_id)
        result = await handler.handle(command)
        return ReturnLoanResponse(
            id=result.id,
            returned_at=result.returned_at,
            was_overdue=result.was_overdue,
        )
    except LoanNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LoanAlreadyReturnedException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LendingException as e:
        raise HTTPException(status_code=400, detail=str(e))

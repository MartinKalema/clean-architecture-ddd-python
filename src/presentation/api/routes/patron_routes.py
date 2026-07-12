"""
Patron API Routes.
"""
from datetime import datetime
from typing import Annotated, List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field, field_validator

from src.application.command_handlers.register_patron import (
    RegisterPatronCommand,
    RegisterPatronHandler,
)
from src.application.command_handlers.reinstate_patron import (
    ReinstatePatronCommand,
    ReinstatePatronHandler,
)
from src.application.command_handlers.suspend_patron import (
    SuspendPatronCommand,
    SuspendPatronHandler,
)
from src.application.command_handlers.upgrade_patron_tier import (
    UpgradePatronTierCommand,
    UpgradePatronTierHandler,
)
from src.application.query_handlers.get_patron import (
    GetPatronHandler,
    GetPatronQuery,
)
from src.application.query_handlers.list_patrons import (
    ListPatronsHandler,
    ListPatronsQuery,
)
from src.container import Container
from src.presentation.api.pagination import set_page_headers

router = APIRouter(prefix="/patrons", tags=["Patrons"])


class PatronCreate(BaseModel):
    """Request model for creating a patron."""
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    membership_tier: str = "regular"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("Invalid email address")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @field_validator("membership_tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        valid_tiers = ["regular", "premium", "researcher"]
        if v.lower() not in valid_tiers:
            raise ValueError(f"Tier must be one of: {valid_tiers}")
        return v.lower()


class SuspendRequest(BaseModel):
    """Request model for suspending a patron."""
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Reason cannot be blank")
        return value


class UpgradeTierRequest(BaseModel):
    """Request model for upgrading patron tier."""
    new_tier: str

    @field_validator("new_tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        valid_tiers = ["regular", "premium", "researcher"]
        if v.lower() not in valid_tiers:
            raise ValueError(f"Tier must be one of: {valid_tiers}")
        return v.lower()


class PatronResponse(BaseModel):
    """Response model for patron."""
    id: str
    name: str
    first_name: str
    last_name: str
    email: str
    membership_tier: str
    is_suspended: bool
    suspended_reason: Optional[str] = None
    registered_at: Optional[datetime] = None


@router.post("", response_model=PatronResponse, status_code=201)
@inject
async def register_patron(
    patron: PatronCreate,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    handler: RegisterPatronHandler = Depends(Provide[Container.register_patron_handler]),
):
    """Register a new patron."""
    command = RegisterPatronCommand(
        first_name=patron.first_name,
        last_name=patron.last_name,
        email=patron.email,
        membership_tier=patron.membership_tier,
        idempotency_key=idempotency_key,
    )
    result = await handler.handle(command)
    return PatronResponse(**result.__dict__)


@router.get("", response_model=List[PatronResponse])
@inject
async def list_patrons(
    response: Response,
    only_suspended: bool = Query(False),
    membership_tier: Optional[str] = Query(None, max_length=16),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    cursor: Optional[str] = Query(None, max_length=1024),
    handler: ListPatronsHandler = Depends(Provide[Container.list_patrons_handler]),
):
    """List patrons with optional filters."""
    query = ListPatronsQuery(
        only_suspended=only_suspended,
        membership_tier=membership_tier,
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
        PatronResponse(
            id=p.id,
            name=p.name,
            first_name=p.first_name,
            last_name=p.last_name,
            email=p.email,
            membership_tier=p.membership_tier,
            is_suspended=p.is_suspended,
            suspended_reason=p.suspended_reason,
            registered_at=p.registered_at,
        )
        for p in page.items
    ]


@router.get("/{patron_id}", response_model=PatronResponse)
@inject
async def get_patron(
    patron_id: str,
    handler: GetPatronHandler = Depends(Provide[Container.get_patron_handler]),
):
    """Get a patron by ID."""
    query = GetPatronQuery(patron_id=patron_id)
    result = await handler.handle(query)
    return PatronResponse(
        id=result.id,
        name=result.name,
        first_name=result.first_name,
        last_name=result.last_name,
        email=result.email,
        membership_tier=result.membership_tier,
        is_suspended=result.is_suspended,
        suspended_reason=result.suspended_reason,
        registered_at=result.registered_at,
    )


@router.post("/{patron_id}/suspend", response_model=PatronResponse)
@inject
async def suspend_patron(
    patron_id: str,
    request: SuspendRequest,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    handler: SuspendPatronHandler = Depends(Provide[Container.suspend_patron_handler]),
):
    """Suspend a patron's borrowing privileges."""
    command = SuspendPatronCommand(
        patron_id=patron_id,
        reason=request.reason,
        idempotency_key=idempotency_key,
    )
    result = await handler.handle(command)
    return PatronResponse(**result.__dict__)


@router.post("/{patron_id}/reinstate", response_model=PatronResponse)
@inject
async def reinstate_patron(
    patron_id: str,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    handler: ReinstatePatronHandler = Depends(Provide[Container.reinstate_patron_handler]),
):
    """Reinstate a suspended patron."""
    command = ReinstatePatronCommand(
        patron_id=patron_id,
        idempotency_key=idempotency_key,
    )
    result = await handler.handle(command)
    return PatronResponse(**result.__dict__)


@router.post("/{patron_id}/upgrade-tier", response_model=PatronResponse)
@inject
async def upgrade_patron_tier(
    patron_id: str,
    request: UpgradeTierRequest,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    handler: UpgradePatronTierHandler = Depends(Provide[Container.upgrade_patron_tier_handler]),
):
    """Upgrade a patron's membership tier."""
    command = UpgradePatronTierCommand(
        patron_id=patron_id,
        new_tier=request.new_tier,
        idempotency_key=idempotency_key,
    )
    result = await handler.handle(command)
    return PatronResponse(**result.__dict__)

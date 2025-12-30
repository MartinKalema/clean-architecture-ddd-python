"""
Patron API Routes.
"""
import re
from datetime import datetime
from typing import List, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

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
from src.domain.patron.exceptions import (
    PatronAlreadySuspendedException,
    PatronException,
    PatronNotFoundException,
    PatronNotSuspendedException,
)

router = APIRouter(prefix="/patrons", tags=["Patrons"])


class PatronCreate(BaseModel):
    """Request model for creating a patron."""
    first_name: str
    last_name: str
    email: str
    membership_tier: str = "regular"

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError("Invalid email address")
        return v

    @field_validator("membership_tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        valid_tiers = ["regular", "premium", "researcher"]
        if v.lower() not in valid_tiers:
            raise ValueError(f"Tier must be one of: {valid_tiers}")
        return v.lower()


class SuspendRequest(BaseModel):
    """Request model for suspending a patron."""
    reason: str


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
    handler: RegisterPatronHandler = Depends(Provide[Container.register_patron_handler]),
):
    """Register a new patron."""
    try:
        command = RegisterPatronCommand(
            first_name=patron.first_name,
            last_name=patron.last_name,
            email=patron.email,
            membership_tier=patron.membership_tier,
        )
        result = await handler.handle(command)
        return PatronResponse(
            id=result.id,
            name=result.name,
            first_name=patron.first_name,
            last_name=patron.last_name,
            email=result.email,
            membership_tier=result.membership_tier,
            is_suspended=False,
        )
    except PatronException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[PatronResponse])
@inject
async def list_patrons(
    only_suspended: bool = Query(False),
    membership_tier: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    handler: ListPatronsHandler = Depends(Provide[Container.list_patrons_handler]),
):
    """List patrons with optional filters."""
    query = ListPatronsQuery(
        only_suspended=only_suspended,
        membership_tier=membership_tier,
        limit=limit,
        offset=offset,
    )
    results = await handler.handle(query)
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
        for p in results
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
    if not result:
        raise HTTPException(status_code=404, detail=f"Patron {patron_id} not found")
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
    handler: SuspendPatronHandler = Depends(Provide[Container.suspend_patron_handler]),
    get_handler: GetPatronHandler = Depends(Provide[Container.get_patron_handler]),
):
    """Suspend a patron's borrowing privileges."""
    try:
        command = SuspendPatronCommand(patron_id=patron_id, reason=request.reason)
        await handler.handle(command)

        patron = await get_handler.handle(GetPatronQuery(patron_id=patron_id))
        return PatronResponse(
            id=patron.id,
            name=patron.name,
            first_name=patron.first_name,
            last_name=patron.last_name,
            email=patron.email,
            membership_tier=patron.membership_tier,
            is_suspended=patron.is_suspended,
            suspended_reason=patron.suspended_reason,
            registered_at=patron.registered_at,
        )
    except PatronNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PatronAlreadySuspendedException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{patron_id}/reinstate", response_model=PatronResponse)
@inject
async def reinstate_patron(
    patron_id: str,
    handler: ReinstatePatronHandler = Depends(Provide[Container.reinstate_patron_handler]),
    get_handler: GetPatronHandler = Depends(Provide[Container.get_patron_handler]),
):
    """Reinstate a suspended patron."""
    try:
        command = ReinstatePatronCommand(patron_id=patron_id)
        await handler.handle(command)

        patron = await get_handler.handle(GetPatronQuery(patron_id=patron_id))
        return PatronResponse(
            id=patron.id,
            name=patron.name,
            first_name=patron.first_name,
            last_name=patron.last_name,
            email=patron.email,
            membership_tier=patron.membership_tier,
            is_suspended=patron.is_suspended,
            suspended_reason=patron.suspended_reason,
            registered_at=patron.registered_at,
        )
    except PatronNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PatronNotSuspendedException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{patron_id}/upgrade-tier", response_model=PatronResponse)
@inject
async def upgrade_patron_tier(
    patron_id: str,
    request: UpgradeTierRequest,
    handler: UpgradePatronTierHandler = Depends(Provide[Container.upgrade_patron_tier_handler]),
    get_handler: GetPatronHandler = Depends(Provide[Container.get_patron_handler]),
):
    """Upgrade a patron's membership tier."""
    try:
        command = UpgradePatronTierCommand(patron_id=patron_id, new_tier=request.new_tier)
        await handler.handle(command)

        patron = await get_handler.handle(GetPatronQuery(patron_id=patron_id))
        return PatronResponse(
            id=patron.id,
            name=patron.name,
            first_name=patron.first_name,
            last_name=patron.last_name,
            email=patron.email,
            membership_tier=patron.membership_tier,
            is_suspended=patron.is_suspended,
            suspended_reason=patron.suspended_reason,
            registered_at=patron.registered_at,
        )
    except PatronNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PatronException as e:
        raise HTTPException(status_code=400, detail=str(e))

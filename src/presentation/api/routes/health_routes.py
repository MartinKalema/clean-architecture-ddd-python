"""
Health check endpoints for monitoring and orchestration.

Provides:
- /health - Basic liveness check
- /health/ready - Readiness check with dependency verification
"""
from fastapi import APIRouter, Depends
from dependency_injector.wiring import inject, Provide
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime

from src.container import Container
from src.infrastructure.external.database import Database

router = APIRouter(prefix="/health", tags=["Health"])


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: str = "1.0.0"
    checks: Optional[Dict[str, Dict[str, str]]] = None


@router.get("", response_model=HealthStatus)
async def liveness():
    """
    Basic liveness check.

    Returns 200 if the application is running.
    Used by load balancers and orchestrators to verify the app is alive.
    """
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/ready", response_model=HealthStatus)
@inject
async def readiness(
    database: Database = Depends(Provide[Container.database])
):
    """
    Readiness check with dependency verification.

    Checks:
    - Database connectivity

    Returns 200 if all dependencies are healthy, 503 otherwise.
    Used by orchestrators to know when the app can receive traffic.
    """
    checks = {}
    all_healthy = True

    # Check database
    try:
        async with database.session_factory() as session:
            await session.execute("SELECT 1")
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    status = "healthy" if all_healthy else "unhealthy"

    response = HealthStatus(
        status=status,
        timestamp=datetime.utcnow().isoformat(),
        checks=checks
    )

    if not all_healthy:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=response.model_dump())

    return response

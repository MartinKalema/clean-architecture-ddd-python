"""
Health check endpoints for monitoring and orchestration.

Provides:
- /health - Liveness check
- /health/ready - Readiness check with dependency verification
- /health/circuits - Circuit breaker status for all external services
"""
from datetime import datetime
from typing import Any, Dict, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from src.container import Container
from src.infrastructure.adapters.resilience import circuit_breaker_registry
from src.infrastructure.external.postgresql import PostgreSQL

router = APIRouter(prefix="/health", tags=["Health"])


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: str = "1.0.0"
    checks: Optional[Dict[str, Dict[str, Any]]] = None


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status response model."""
    timestamp: str
    circuits: Dict[str, Dict[str, Any]]
    unhealthy: list[str]


@router.get("", response_model=HealthStatus)
async def liveness():
    """
    Liveness check.

    Returns 200 if the application is running.
    Used by load balancers, K8s, and orchestrators to verify the app is alive.
    """
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/live", response_model=HealthStatus)
async def live():
    """
    Lightweight liveness check - no dependency checks.

    Use this for high-frequency health checks from load balancers.
    Does not check database or other dependencies.
    """
    return HealthStatus(
        status="healthy",
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/ready", response_model=HealthStatus)
@inject
async def readiness(
    postgresql: PostgreSQL = Depends(Provide[Container.postgresql])
):
    """
    Readiness check with dependency verification.

    Checks:
    - Database connectivity
    - Circuit breaker states (warns but doesn't fail)

    Returns 200 if all critical dependencies are healthy, 503 otherwise.
    Used by orchestrators to know when the app can receive traffic.
    """
    checks: Dict[str, Dict[str, Any]] = {}
    all_healthy = True

    try:
        async with postgresql.session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgresql"] = {"status": "healthy"}
    except Exception as e:
        checks["postgresql"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    unhealthy_circuits = circuit_breaker_registry.get_unhealthy()
    if unhealthy_circuits:
        checks["circuit_breakers"] = {
            "status": "degraded",
            "open_circuits": unhealthy_circuits,
            "message": "Some external services are unavailable"
        }
    else:
        checks["circuit_breakers"] = {"status": "healthy"}

    status = "healthy" if all_healthy else "unhealthy"

    response = HealthStatus(
        status=status,
        timestamp=datetime.utcnow().isoformat(),
        checks=checks
    )

    if not all_healthy:
        raise HTTPException(status_code=503, detail=response.model_dump())

    return response


@router.get("/circuits", response_model=CircuitBreakerStatus)
async def circuit_breakers():
    """
    Get detailed status of all circuit breakers.

    Use this endpoint to monitor the health of external service integrations:
    - SendGrid email service
    - Elasticsearch (read-model search)

    Circuit breaker states:
    - closed: Normal operation
    - open: Service is down, failing fast
    - half_open: Testing if service has recovered

    Returns 200 always (this is informational only).
    """
    all_status = circuit_breaker_registry.get_all_status()
    unhealthy = circuit_breaker_registry.get_unhealthy()

    return CircuitBreakerStatus(
        timestamp=datetime.utcnow().isoformat(),
        circuits=all_status,
        unhealthy=unhealthy
    )

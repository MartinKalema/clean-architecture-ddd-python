"""
Health check endpoints for monitoring and orchestration.

Provides:
- /health - Liveness check
- /health/ready - Readiness check with dependency verification
- /health/circuits - Circuit breaker status for all external services
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.container import Container

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
        timestamp=datetime.now(timezone.utc).isoformat()
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
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/ready", response_model=HealthStatus)
@inject
async def readiness(
    postgresql=Depends(Provide[Container.postgresql]),
    registry=Depends(Provide[Container.circuit_breaker_registry]),
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
        await postgresql.ping()
        checks["postgresql"] = {"status": "healthy"}
    except Exception as e:
        checks["postgresql"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    unhealthy_circuits = registry.get_unhealthy()
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
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks
    )

    if not all_healthy:
        raise HTTPException(status_code=503, detail=response.model_dump())

    return response


@router.get("/circuits", response_model=CircuitBreakerStatus)
@inject
async def circuit_breakers(
    registry=Depends(Provide[Container.circuit_breaker_registry]),
):
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
    all_status = registry.get_all_status()
    unhealthy = registry.get_unhealthy()

    return CircuitBreakerStatus(
        timestamp=datetime.now(timezone.utc).isoformat(),
        circuits=all_status,
        unhealthy=unhealthy
    )

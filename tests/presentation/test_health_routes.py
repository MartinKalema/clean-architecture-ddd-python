"""Operational endpoints must not expose dependency internals."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.presentation.api.routes.health_routes import readiness


@pytest.mark.asyncio
async def test_readiness_redacts_database_exception_details():
    database = MagicMock()
    database.ping = AsyncMock(
        side_effect=RuntimeError(
            "password=super-secret host=internal-db.example"
        )
    )
    registry = MagicMock()
    registry.get_unhealthy.return_value = []
    logger = MagicMock()

    response = await readiness(
        postgresql=database,
        registry=registry,
        logger=logger,
    )

    assert response.status_code == 503
    detail = json.loads(response.body)
    assert detail["checks"]["postgresql"]["error"] == "dependency unavailable"
    assert "super-secret" not in str(detail)
    assert "internal-db" not in str(detail)
    logger.error.assert_called_once()

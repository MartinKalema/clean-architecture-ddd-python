"""API operational lifecycle and exception-mapping contracts."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.exceptions import InvalidIdempotencyKeyException
from src.presentation.api.main import application_exception_handler, lifespan


@pytest.mark.asyncio
async def test_lifespan_closes_every_process_owned_client():
    database = MagicMock()
    database.verify_schema_current = AsyncMock()
    database.dispose = AsyncMock()
    redis = MagicMock()
    redis.close = AsyncMock()
    elasticsearch = MagicMock()
    elasticsearch.close = AsyncMock()
    projection_freshness = MagicMock()
    projection_freshness.close = AsyncMock()
    etcd = MagicMock()
    logger = MagicMock()
    configurations = MagicMock()
    configurations.elasticsearch.enabled.return_value = True
    container = SimpleNamespace(
        postgresql=MagicMock(return_value=database),
        redis_client=MagicMock(return_value=redis),
        elasticsearch_client=MagicMock(return_value=elasticsearch),
        projection_freshness=MagicMock(return_value=projection_freshness),
        etcd_adapter=MagicMock(return_value=etcd),
        logger=MagicMock(return_value=logger),
        configurations=configurations,
        sendgrid_circuit_breaker=MagicMock(),
        elasticsearch_circuit_breaker=MagicMock(),
    )
    app = SimpleNamespace(container=container)

    async with lifespan(app):
        database.verify_schema_current.assert_awaited_once()

    redis.close.assert_awaited_once()
    elasticsearch.close.assert_awaited_once()
    projection_freshness.close.assert_awaited_once()
    database.dispose.assert_awaited_once()
    etcd.close.assert_called_once()
    container.sendgrid_circuit_breaker.assert_not_called()
    container.elasticsearch_circuit_breaker.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_closes_every_resource_when_schema_verification_fails():
    database = MagicMock()
    database.verify_schema_current = AsyncMock(side_effect=RuntimeError("bad schema"))
    database.dispose = AsyncMock()
    redis = MagicMock(close=AsyncMock())
    elasticsearch = MagicMock(close=AsyncMock())
    projection_freshness = MagicMock(close=AsyncMock())
    etcd = MagicMock()
    logger = MagicMock()
    configurations = MagicMock()
    configurations.elasticsearch.enabled.return_value = True
    container = SimpleNamespace(
        postgresql=MagicMock(return_value=database),
        redis_client=MagicMock(return_value=redis),
        elasticsearch_client=MagicMock(return_value=elasticsearch),
        projection_freshness=MagicMock(return_value=projection_freshness),
        etcd_adapter=MagicMock(return_value=etcd),
        logger=MagicMock(return_value=logger),
        configurations=configurations,
        elasticsearch_circuit_breaker=MagicMock(),
    )

    with pytest.raises(RuntimeError, match="bad schema"):
        async with lifespan(SimpleNamespace(container=container)):
            pytest.fail("startup must not yield")

    projection_freshness.close.assert_awaited_once()
    elasticsearch.close.assert_awaited_once()
    redis.close.assert_awaited_once()
    database.dispose.assert_awaited_once()
    etcd.close.assert_called_once()
    container.elasticsearch_circuit_breaker.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_idempotency_key_maps_to_validation_error():
    response = await application_exception_handler(
        MagicMock(),
        InvalidIdempotencyKeyException(),
    )

    assert response.status_code == 422
    assert json.loads(response.body)["error"]["code"] == "validation_error"

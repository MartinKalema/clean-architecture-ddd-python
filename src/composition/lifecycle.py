"""Centralized process resource startup and reverse-order shutdown."""
from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _OwnedResource:
    name: str
    close: Callable[[], Any]


class ManagedResources:
    """Own resources created by one process and close all of them exactly once."""

    def __init__(self, logger: Any) -> None:
        self._logger = logger
        self._resources: list[_OwnedResource] = []
        self._closed = False

    def own(self, name: str, resource: Any, close_method: str) -> Any:
        close = getattr(resource, close_method)
        self._resources.append(_OwnedResource(name=name, close=close))
        return resource

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for owned in reversed(self._resources):
            try:
                result = owned.close()
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                self._logger.error(
                    f"Failed to close {owned.name} resource",
                    exception=error,
                )

    async def __aenter__(self) -> "ManagedResources":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.close()


def _resources(container: Any) -> ManagedResources:
    resources = ManagedResources(container.logger())
    resources.own("etcd", container.etcd_adapter(), "close")
    return resources


def cli_resources(container: Any) -> ManagedResources:
    """Own every transport that a CLI command may resolve lazily."""
    resources = _resources(container)
    resources.own("postgresql", container.postgresql(), "dispose")
    resources.own("redis", container.redis_client(), "close")
    resources.own("elasticsearch", container.elasticsearch_client(), "close")
    resources.own(
        "projection freshness", container.projection_freshness(), "close"
    )
    return resources


@asynccontextmanager
async def api_resources(container: Any) -> AsyncIterator[Any]:
    resources = _resources(container)
    async with resources:
        database = resources.own("postgresql", container.postgresql(), "dispose")
        resources.own("redis", container.redis_client(), "close")
        resources.own("elasticsearch", container.elasticsearch_client(), "close")
        resources.own(
            "projection freshness", container.projection_freshness(), "close"
        )
        await database.verify_schema_current()
        # Only enabled, API-owned integrations belong in the local registry.
        if container.configurations.elasticsearch.enabled():
            container.elasticsearch_circuit_breaker()
        yield database


@asynccontextmanager
async def workflow_resources(container: Any) -> AsyncIterator[Any]:
    resources = _resources(container)
    async with resources:
        database = resources.own("postgresql", container.postgresql(), "dispose")
        resources.own("redis", container.redis_client(), "close")
        consumer = resources.own(
            "workflow consumer", container.domain_event_consumer(), "stop"
        )
        await database.verify_schema_current()
        yield consumer


@asynccontextmanager
async def notification_resources(container: Any) -> AsyncIterator[Any]:
    resources = _resources(container)
    async with resources:
        database = resources.own("postgresql", container.postgresql(), "dispose")
        consumer = resources.own(
            "notification consumer",
            container.notification_event_consumer(),
            "stop",
        )
        await database.verify_schema_current()
        yield consumer


@asynccontextmanager
async def projection_resources(container: Any) -> AsyncIterator[Any]:
    resources = _resources(container)
    async with resources:
        resources.own("redis", container.redis_client(), "close")
        consumer = resources.own(
            "projection consumer", container.elasticsearch_sync_consumer(), "stop"
        )
        yield consumer


@asynccontextmanager
async def database_resources(container: Any) -> AsyncIterator[Any]:
    """Own etcd and PostgreSQL for reapers and short-lived maintenance jobs."""
    resources = _resources(container)
    async with resources:
        database = resources.own("postgresql", container.postgresql(), "dispose")
        await database.verify_schema_current()
        yield database


@asynccontextmanager
async def search_maintenance_resources(
    container: Any,
) -> AsyncIterator[tuple[Any, Any]]:
    """Own the database and Elasticsearch clients for a reindex operation."""
    resources = _resources(container)
    async with resources:
        database = resources.own("postgresql", container.postgresql(), "dispose")
        elasticsearch = resources.own(
            "elasticsearch", container.elasticsearch_client(), "close"
        )
        await database.verify_schema_current()
        yield database, elasticsearch


@asynccontextmanager
async def kafka_maintenance_resources(container: Any) -> AsyncIterator[Any]:
    """Own the application Kafka client for a bounded maintenance operation."""
    resources = _resources(container)
    async with resources:
        kafka = resources.own("kafka", container.kafka_client(), "close")
        yield kafka

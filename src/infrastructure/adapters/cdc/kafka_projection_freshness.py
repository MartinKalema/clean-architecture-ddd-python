"""Kafka consumer-lag gate for optional Elasticsearch read models."""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.structs import TopicPartition

if TYPE_CHECKING:
    from src.application.ports import ILogger


class KafkaProjectionFreshness:
    """Allow ES reads only when every CDC partition is fully committed."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        logger: ILogger | None = None,
        cache_seconds: float = 1.0,
    ) -> None:
        if not bootstrap_servers.strip() or not group_id.strip() or not topics:
            raise ValueError("projection freshness requires Kafka/group/topics")
        if not 0 <= cache_seconds <= 30:
            raise ValueError("cache_seconds must be between 0 and 30")
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._topics = tuple(sorted(set(topics)))
        self._logger = logger
        self._cache_seconds = cache_seconds
        self._admin: AIOKafkaAdminClient | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._connect_lock = asyncio.Lock()
        self._cached_until = 0.0
        self._cached_fresh = False

    async def is_fresh(self) -> bool:
        now = time.monotonic()
        if now < self._cached_until:
            return self._cached_fresh
        try:
            await self._ensure_connected()
            assert self._admin is not None and self._consumer is not None
            partitions: list[TopicPartition] = []
            for topic in self._topics:
                partition_ids = self._consumer.partitions_for_topic(topic)
                if partition_ids is None:
                    self._cache(False, now)
                    return False
                partitions.extend(
                    TopicPartition(topic, partition_id)
                    for partition_id in sorted(partition_ids)
                )
            committed = await self._admin.list_consumer_group_offsets(
                self._group_id,
                partitions=partitions,
            )
            end_offsets = await self._consumer.end_offsets(partitions)
            fresh = all(
                end_offsets[partition] == 0
                or (
                    partition in committed
                    and committed[partition].offset >= end_offsets[partition]
                )
                for partition in partitions
            )
        except Exception as error:
            fresh = False
            if self._logger:
                self._logger.warning(
                    f"Cannot verify Elasticsearch projection lag; using "
                    f"PostgreSQL fallback: {error}"
                )
        self._cache(fresh, now)
        return fresh

    async def _ensure_connected(self) -> None:
        if self._admin is not None and self._consumer is not None:
            return
        async with self._connect_lock:
            if self._admin is None:
                admin = AIOKafkaAdminClient(
                    bootstrap_servers=self._bootstrap_servers
                )
                await admin.start()
                self._admin = admin
            if self._consumer is None:
                consumer = AIOKafkaConsumer(
                    bootstrap_servers=self._bootstrap_servers,
                    enable_auto_commit=False,
                )
                await consumer.start()
                self._consumer = consumer

    def _cache(self, fresh: bool, now: float) -> None:
        self._cached_fresh = fresh
        self._cached_until = now + self._cache_seconds

    async def close(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._admin is not None:
            await self._admin.close()
            self._admin = None

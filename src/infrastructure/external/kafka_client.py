"""
Kafka Client - External service wrapper for Apache Kafka.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import math
import time
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Optional

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError
from aiokafka.structs import OffsetAndMetadata, TopicPartition

from src.infrastructure.exceptions import (
    DurableMessageHandlingException,
    MessageBrokerException,
    UnrecoverableMessageException,
)

if TYPE_CHECKING:
    from src.application.ports import ILogger

# How often the consume loop logs consumer lag (staleness of the pipeline).
LAG_LOG_INTERVAL_SECONDS = 60.0
DLQ_PARK_TIMEOUT_SECONDS = 60.0
# The durable handler inbox owns a claim for 300 seconds by default. Leave a
# full minute for cancellation/rollback and completion-record persistence so a
# second consumer can never acquire the same handler claim while the first one
# is still finishing after its transport deadline.
MAX_MESSAGE_PROCESSING_TIMEOUT_SECONDS = 240.0
_DLQ_BINARY_FIELD = "__kafka_bytes_base64__"


class KafkaClient:
    """
    Async client for Kafka messaging operations.

    Provides producer and consumer functionality with JSON serialization.
    Configuration is loaded from etcd via dependency injection.

    Consumption is at-least-once: offsets are committed only after a message
    has been handled successfully (or parked on a dead-letter topic after
    exhausting retries). Handlers must therefore be idempotent.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        consumer_max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        consumer_max_poll_interval_ms: int = 900_000,
        message_processing_timeout_seconds: float = 180.0,
        internal_topic_replication_factor: int = 3,
        logger: Optional[ILogger] = None,
    ):
        if isinstance(consumer_max_retries, bool) or consumer_max_retries < 0:
            raise ValueError("consumer_max_retries must be non-negative")
        if (
            isinstance(retry_backoff_seconds, bool)
            or not math.isfinite(retry_backoff_seconds)
            or retry_backoff_seconds < 0
        ):
            raise ValueError("retry_backoff_seconds must be non-negative")
        if (
            isinstance(consumer_max_poll_interval_ms, bool)
            or consumer_max_poll_interval_ms < 1_000
        ):
            raise ValueError("consumer_max_poll_interval_ms must be at least 1000")
        if (
            isinstance(message_processing_timeout_seconds, bool)
            or not math.isfinite(message_processing_timeout_seconds)
            or message_processing_timeout_seconds <= 0
            or message_processing_timeout_seconds
            > MAX_MESSAGE_PROCESSING_TIMEOUT_SECONDS
        ):
            raise ValueError(
                "message_processing_timeout_seconds must be greater than zero "
                f"and at most {MAX_MESSAGE_PROCESSING_TIMEOUT_SECONDS:g} to "
                "remain below the handler inbox lease"
            )
        if (
            isinstance(internal_topic_replication_factor, bool)
            or not 1 <= internal_topic_replication_factor <= 32_767
        ):
            raise ValueError(
                "internal_topic_replication_factor must be between 1 and 32767"
            )

        # One poll cycle includes the initial attempt plus bounded in-process
        # retries. Durable messages leave their offset uncommitted after this
        # budget and are retried by the supervised worker after restart. Keeping
        # the complete cycle below max.poll.interval prevents a retrying worker
        # from becoming a group zombie while another member processes its lease.
        retry_delay_budget = sum(
            min(retry_backoff_seconds * (2 ** min(attempt, 10)), 60.0)
            for attempt in range(consumer_max_retries)
        )
        poll_cycle_budget = (
            message_processing_timeout_seconds * (consumer_max_retries + 1)
            + retry_delay_budget
            + DLQ_PARK_TIMEOUT_SECONDS
            + 5.0
        )
        if poll_cycle_budget * 1_000 >= consumer_max_poll_interval_ms:
            raise ValueError(
                "Kafka max poll interval must exceed the worst-case message "
                "processing and retry budget"
            )

        self._bootstrap_servers = bootstrap_servers
        self._consumer_max_retries = consumer_max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._consumer_max_poll_interval_ms = consumer_max_poll_interval_ms
        self._message_processing_timeout_seconds = message_processing_timeout_seconds
        self._internal_topic_replication_factor = internal_topic_replication_factor
        self._logger = logger
        self._producer: Optional[AIOKafkaProducer] = None
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._ensured_topics: set[str] = set()

    async def connect_producer(self) -> None:
        """Establish producer connection to Kafka."""
        if self._producer is None:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                # DLQ publication is the durability boundary before the source
                # offset is committed. Idempotence also forces acks="all" and
                # prevents producer retries from creating duplicate records.
                enable_idempotence=True,
            )
            await self._producer.start()
            if self._logger:
                self._logger.info(f"Kafka producer connected to {self._bootstrap_servers}")

    async def connect_consumer(
        self,
        topics: list[str],
        group_id: str,
        auto_offset_reset: str = "earliest",
    ) -> None:
        """
        Establish consumer connection to Kafka.

        Auto-commit is disabled: offsets are committed by consume() only
        after a message has been fully handled, so a crash mid-message
        redelivers it instead of silently dropping it.
        """
        if self._consumer is None:
            self._consumer = AIOKafkaConsumer(
                *topics,
                bootstrap_servers=self._bootstrap_servers,
                group_id=group_id,
                auto_offset_reset=auto_offset_reset,
                enable_auto_commit=False,
                max_poll_interval_ms=self._consumer_max_poll_interval_ms,
            )
            await self._consumer.start()
            if self._logger:
                self._logger.info(f"Kafka consumer connected to {self._bootstrap_servers}, topics: {topics}")

    async def close(self) -> None:
        """Close all Kafka connections."""
        if self._producer:
            await self._producer.stop()
            self._producer = None
            if self._logger:
                self._logger.info("Kafka producer disconnected")

        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
            if self._logger:
                self._logger.info("Kafka consumer disconnected")

    async def send(
        self,
        topic: str,
        value: Any,
        key: Any = None,
    ) -> bool:
        """JSON-encode and send a message to a Kafka topic."""
        try:
            encoded_value = json.dumps(value).encode("utf-8")
            encoded_key = (
                json.dumps(key).encode("utf-8") if key is not None else None
            )
        except (TypeError, ValueError) as error:
            if self._logger:
                self._logger.error(
                    f"Kafka serialization error for {topic}: {error}"
                )
            return False
        return await self.send_raw(topic, value=encoded_value, key=encoded_key)

    async def send_raw(
        self,
        topic: str,
        *,
        value: bytes | None,
        key: bytes | None = None,
    ) -> bool:
        """Send already-encoded bytes, preserving poison records for replay."""
        if not self._producer:
            await self.connect_producer()
        assert self._producer is not None

        try:
            await self._producer.send_and_wait(topic, value=value, key=key)
            return True
        except Exception as e:
            if self._logger:
                self._logger.error(f"Kafka send error: {e}")
            return False

    async def consume(
        self,
        handler: Callable[[str, dict | None, dict | None], Any],
        *,
        retry_forever: bool = False,
        park_unrecoverable: bool = True,
    ) -> AsyncIterator[None]:
        """
        Consume messages with at-least-once semantics and yield after each.

        Each message is retried with exponential backoff. Generic consumers
        can dead-letter after the configured attempts; correctness-critical
        consumers leave the offset uncommitted after one bounded poll cycle so
        the supervisor restarts them and Kafka redelivers until success.
        Structurally unrecoverable messages are always parked on <topic>.dlq.
        If the dead-letter publish itself fails, the consumer raises without
        committing and the message is redelivered on restart.

        Args:
            handler: Async callback function(topic, key, value) for each message
            retry_forever: Preserve transient failures for supervised redelivery
                           instead of dead-lettering after this poll-cycle budget.
            park_unrecoverable: Park structural poison and advance. Projection
                                consumers set this false so a malformed CDC row
                                keeps lag nonzero and forces authoritative reads.
        """
        if not self._consumer:
            raise RuntimeError("Consumer not connected. Call connect_consumer first.")

        last_lag_log = time.monotonic()

        async for record in self._consumer:
            await self._handle_with_retry(
                record,
                handler,
                retry_forever=retry_forever,
                park_unrecoverable=park_unrecoverable,
            )
            # Commit only this record's partition. This remains correct if the
            # implementation later prefetches or processes other partitions in
            # parallel; a generic commit() would acknowledge every fetched
            # position, including work that may not have completed yet.
            partition = TopicPartition(record.topic, record.partition)
            await self._consumer.commit(
                {partition: OffsetAndMetadata(record.offset + 1, "")}
            )

            if time.monotonic() - last_lag_log >= LAG_LOG_INTERVAL_SECONDS:
                await self._log_consumer_lag()
                last_lag_log = time.monotonic()

            yield

    async def _handle_with_retry(
        self,
        record,
        handler,
        *,
        retry_forever: bool = False,
        park_unrecoverable: bool = True,
    ) -> None:
        """Invoke the handler, retrying with backoff; dead-letter on exhaustion."""
        attempt = 0
        while True:
            try:
                # AIOKafka must yield raw bytes. Decoding here keeps malformed
                # UTF-8/JSON inside the same retry, DLQ, and offset-commit
                # boundary as handler failures instead of crashing iteration
                # before the record can be identified and parked.
                key = _decode_json_field(record.key, field="key")
                value = _decode_json_field(record.value, field="value")
                await asyncio.wait_for(
                    handler(record.topic, key, value),
                    timeout=self._message_processing_timeout_seconds,
                )
                return
            except Exception as e:
                if isinstance(e, UnrecoverableMessageException):
                    if not park_unrecoverable:
                        if self._logger:
                            self._logger.error(
                                f"Projection poison from {record.topic} "
                                f"(offset {record.offset}) is left uncommitted "
                                "so reads fall back until the contract is repaired"
                            )
                        raise
                    await self._park_on_dead_letter(record, e)
                    return
                durable_retry = retry_forever or isinstance(
                    e, DurableMessageHandlingException
                )
                if attempt < self._consumer_max_retries:
                    backoff = min(
                        self._retry_backoff_seconds * (2 ** min(attempt, 10)),
                        60.0,
                    )
                    if self._logger:
                        retry_label = (
                            "until success"
                            if durable_retry
                            else f"{attempt + 1}/{self._consumer_max_retries}"
                        )
                        self._logger.warning(
                            f"Error processing message from {record.topic} "
                            f"(offset {record.offset}), retry {retry_label}: {e}. "
                            f"Retrying in {backoff:.1f}s"
                        )
                    await asyncio.sleep(backoff)
                elif durable_retry:
                    # Never turn a committed workflow/projection obligation into
                    # a business cancellation or DLQ merely because a dependency
                    # remained unavailable for one poll cycle. Raising exits the
                    # supervised worker without committing; Kafka redelivers the
                    # same record after restart, while the bounded cycle avoids
                    # exceeding max.poll.interval inside this consumer member.
                    if self._logger:
                        self._logger.error(
                            f"Durable message from {record.topic} "
                            f"(offset {record.offset}) exhausted the in-process "
                            "retry budget; leaving its offset uncommitted"
                        )
                    raise
                else:
                    await self._park_on_dead_letter(record, e)
                    return
                attempt += 1

    async def _park_on_dead_letter(self, record, error: Exception) -> None:
        """Bound DLQ administration/produce time inside the current poll cycle."""
        try:
            await asyncio.wait_for(
                self._send_to_dead_letter(record, error),
                timeout=DLQ_PARK_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as timeout_error:
            # The idempotent producer may still have accepted the record. Do not
            # commit the source offset: redelivery can create a duplicate DLQ
            # wrapper, but downstream inbox/version fencing makes that safe;
            # committing here could lose the only recoverable copy.
            raise MessageBrokerException(
                f"Timed out parking message from {record.topic} "
                f"(offset {record.offset})",
                original_exception=error,
            ) from timeout_error

    async def _ensure_topic(self, topic: str, partitions: int = 1) -> None:
        """
        Create an app-owned internal topic (DLQ) if it does not exist.

        The broker runs with auto-create disabled (production posture), so
        the component that owns a topic creates it: Debezium declares its
        data topics via topic.creation.*, and the messaging layer creates
        its dead-letter topics here on first use.
        """
        if topic in self._ensured_topics:
            return

        admin = AIOKafkaAdminClient(bootstrap_servers=self._bootstrap_servers)
        await admin.start()
        try:
            try:
                await admin.create_topics(
                    [
                        NewTopic(
                            name=topic,
                            num_partitions=partitions,
                            replication_factor=self._internal_topic_replication_factor,
                        )
                    ]
                )
                if self._logger:
                    self._logger.info(f"Created topic {topic}")
            except TopicAlreadyExistsError:
                pass

            # TopicAlreadyExists is not proof that a pre-created topic satisfies
            # this process's durability contract. Refuse to park-and-commit when
            # an operator accidentally supplied too few partitions or replicas.
            descriptions = await admin.describe_topics([topic])
            description = next(
                (
                    candidate
                    for candidate in descriptions
                    if candidate.get("topic") == topic
                ),
                None,
            )
            topic_partitions = (
                description.get("partitions", []) if description else []
            )
            if len(topic_partitions) < partitions or any(
                len(partition.get("replicas", []))
                < self._internal_topic_replication_factor
                for partition in topic_partitions
            ):
                raise MessageBrokerException(
                    f"Internal topic {topic!r} does not satisfy "
                    f"partitions>={partitions} and replication_factor>="
                    f"{self._internal_topic_replication_factor}"
                )
        finally:
            await admin.close()

        self._ensured_topics.add(topic)

    async def _send_to_dead_letter(self, record, error: Exception) -> None:
        """Park an unprocessable message on the topic's dead-letter queue."""
        dlq_topic = f"{record.topic}.dlq"
        await self._ensure_topic(dlq_topic)
        message = {
            "original_topic": record.topic,
            "partition": record.partition,
            "offset": record.offset,
            # Consumer records are raw bytes. Store them losslessly in a
            # JSON-safe envelope so malformed UTF-8/JSON can still be
            # inspected and replayed byte-for-byte after repair.
            "key": encode_dead_letter_field(record.key),
            "value": encode_dead_letter_field(record.value),
            "error": str(error),
        }

        if self._logger:
            self._logger.error(
                f"Message from {record.topic} (offset {record.offset}) failed "
                f"after {self._consumer_max_retries} retries; "
                f"sending to {dlq_topic}: {error}"
            )

        delivered = await self.send(
            dlq_topic,
            message,
            key=encode_dead_letter_field(record.key),
        )
        if not delivered:
            # Better to crash without committing (message redelivers on
            # restart) than to commit and lose it.
            raise MessageBrokerException(
                f"Failed to dead-letter message from {record.topic} "
                f"(offset {record.offset})",
                original_exception=error,
            )

    async def _log_consumer_lag(self) -> None:
        """Log per-partition consumer lag — the pipeline's staleness metric."""
        if not self._consumer or not self._logger:
            return

        try:
            lag = await self.get_consumer_lag()
            total = sum(lag.values())
            self._logger.info(f"Consumer lag: total={total}, partitions={lag}")
        except Exception as e:
            self._logger.warning(f"Could not compute consumer lag: {e}")

    async def get_consumer_lag(self) -> dict[str, int]:
        """Return lag (highwater - position) per assigned partition."""
        if not self._consumer:
            return {}

        lag: dict[str, int] = {}
        for tp in self._consumer.assignment():
            highwater = self._consumer.highwater(tp)
            if highwater is None:
                continue
            position = await self._consumer.position(tp)
            lag[f"{tp.topic}[{tp.partition}]"] = max(0, highwater - position)
        return lag

    @property
    def is_producer_connected(self) -> bool:
        """Check if producer is connected."""
        return self._producer is not None

    @property
    def is_consumer_connected(self) -> bool:
        """Check if consumer is connected."""
        return self._consumer is not None


def _decode_json_field(value: Any, *, field: str) -> Any:
    """Decode one raw Kafka field or pass through test/adapter objects."""
    if value is None or not isinstance(value, (bytes, bytearray, memoryview)):
        return value
    try:
        return json.loads(bytes(value).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnrecoverableMessageException(
            f"Malformed Kafka {field}: expected UTF-8 JSON",
            original_exception=error,
        ) from error


def encode_dead_letter_field(value: Any) -> Any:
    """Make raw Kafka bytes JSON-safe without changing their contents."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {
            _DLQ_BINARY_FIELD: base64.b64encode(bytes(value)).decode("ascii")
        }
    return value


def decode_dead_letter_field(value: Any) -> tuple[Any, bool]:
    """Restore an encoded DLQ field and report whether it contained bytes."""
    if not (
        isinstance(value, dict)
        and set(value) == {_DLQ_BINARY_FIELD}
        and isinstance(value[_DLQ_BINARY_FIELD], str)
    ):
        return value, False
    try:
        raw = base64.b64decode(value[_DLQ_BINARY_FIELD], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("DLQ record contains invalid base64 Kafka bytes") from error
    return raw, True

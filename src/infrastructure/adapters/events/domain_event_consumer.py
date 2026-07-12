"""
Domain Event Consumer

Consumes domain events from the outbox Kafka topics (published by the
Debezium Outbox Event Router) and dispatches them to application-layer
event handlers.

Flow:
    UoW commit -> outbox table -> Debezium (WAL) -> Kafka
        -> this consumer -> EventDispatcher -> application event handlers

Delivery is at-least-once: Kafka may redeliver a message after a consumer
restart, so all subscribed handlers must be idempotent.
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Optional

from src.application.ports import EventDeliveryIdentity
from src.domain.catalog import (
    CatalogBookReleased,
    CatalogBookReserved,
)
from src.domain.lending import LoanCompleted, LoanCreated
from src.infrastructure.adapters.events.delivery_store import EventQuarantine
from src.infrastructure.adapters.events.event_registry import (
    EventContractError,
    InvalidEventEnvelopeError,
    deserialize_event,
)
from src.infrastructure.exceptions import (
    DurableMessageHandlingException,
    UnrecoverableMessageException,
)

if TYPE_CHECKING:
    from src.application.ports import IEventDispatcher, ILogger
    from src.infrastructure.external.kafka_client import KafkaClient

# One topic per aggregate type, as routed by the Debezium Outbox Event Router
# (outbox.event.<aggregatetype>).
OUTBOX_TOPICS = [
    "outbox.event.book",
    "outbox.event.patron",
    "outbox.event.loan",
]

# These events mutate another aggregate/context. Once their source fact is
# committed they must converge; notification/projection events retain bounded
# retries and DLQ behavior so an optional dependency cannot block workflows.
DURABLE_TRANSITION_EVENTS = (
    CatalogBookReserved,
    CatalogBookReleased,
    LoanCreated,
    LoanCompleted,
)


class DomainEventConsumer:
    """Consumes outbox events from Kafka and dispatches them to handlers."""

    def __init__(
        self,
        kafka_client: KafkaClient,
        event_dispatcher: IEventDispatcher,
        logger: ILogger,
        topics: Optional[list[str]] = None,
        quarantine: Optional[EventQuarantine] = None,
        group_id: str = "domain-workflow-worker-v1",
        durable_delivery: bool = False,
    ) -> None:
        if not group_id.strip():
            raise ValueError("Kafka consumer group_id cannot be blank")
        self._kafka = kafka_client
        self._dispatcher = event_dispatcher
        self._logger = logger
        self._topics = topics or OUTBOX_TOPICS
        self._quarantine = quarantine
        self._group_id = group_id
        self._durable_delivery = durable_delivery
        self._running = False

    async def _process_message(
        self, topic: str, key: dict | str | None, value: dict | None
    ) -> None:
        """Deserialize one outbox message and dispatch the domain event."""
        if value is None:
            return

        try:
            event = deserialize_event(value)
        except EventContractError as error:
            if self._quarantine is None:
                raise UnrecoverableMessageException(
                    f"Unsupported domain event on {topic}: {error}",
                    original_exception=error,
                ) from error
            try:
                quarantine_id = await self._quarantine.quarantine(
                    topic=topic,
                    message_key=key,
                    payload=value,
                    reason=str(error),
                    event_id=error.event_id,
                    contract_name=error.contract_name,
                    contract_version=error.contract_version,
                )
            except Exception as quarantine_error:
                raise DurableMessageHandlingException(
                    f"Could not quarantine unsupported event from {topic}",
                    original_exception=quarantine_error,
                ) from quarantine_error
            self._logger.warning(
                f"Quarantined unsupported event from {topic} "
                f"(quarantine_id={quarantine_id}); parking source record for replay"
            )
            # Persist a searchable diagnostic record, then ask KafkaClient to
            # park the original record (including partition/offset) on its
            # replayable DLQ. Returning here would commit and strand a future
            # schema after a rolling deployment.
            raise UnrecoverableMessageException(
                f"Unsupported domain event quarantined as {quarantine_id}",
                original_exception=error,
            ) from error

        self._logger.info(
            f"Dispatching {event.event_type} (event_id={event.event_id})"
        )
        try:
            await self._dispatcher.dispatch(
                event,
                delivery_identity=_delivery_identity(value),
            )
        except Exception as error:
            if isinstance(event, DURABLE_TRANSITION_EVENTS):
                raise DurableMessageHandlingException(
                    f"State transition {event.event_type} has not converged",
                    original_exception=error,
                ) from error
            raise

    async def start(self) -> None:
        """Start the consumer loop."""
        self._logger.info(f"Connecting to Kafka, topics: {self._topics}")

        await self._kafka.connect_consumer(
            topics=self._topics,
            group_id=self._group_id,
        )

        self._running = True
        self._logger.info("Starting domain event consumer loop...")

        try:
            async for _ in self._kafka.consume(
                handler=self._process_message,
                retry_forever=self._durable_delivery,
            ):
                if not self._running:
                    break
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        await self._kafka.close()
        self._logger.info("Domain event consumer stopped")


def _delivery_identity(value: dict) -> EventDeliveryIdentity:
    raw_contract = value.get("contract")
    if not isinstance(raw_contract, dict):
        raise InvalidEventEnvelopeError("Event contract must be an object")
    namespace = raw_contract.get("namespace")
    name = raw_contract.get("name")
    version = raw_contract.get("version")
    contract_name = f"{namespace}.{name}"
    contract_version = int(version)
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return EventDeliveryIdentity(
        contract_name=contract_name,
        contract_version=contract_version,
        payload_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )

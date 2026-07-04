"""
Transactional Outbox table for the Debezium Outbox Event Router.

Domain events are inserted into this table in the SAME transaction as the
aggregate changes, so "state changed" and "event owed" commit atomically —
this closes the dual-write gap of publishing after commit. Debezium tails
the WAL, sees the inserts, and routes each row to the Kafka topic
`outbox.event.<aggregatetype>` where the event worker consumes it.

Column names follow the Debezium Outbox Event Router defaults
(id, aggregatetype, aggregateid, type, payload) so no field mapping is
needed in the connector config. Rows are append-only; they are never read
by the application and can be pruned by a retention job once Debezium's
replication slot has advanced past them.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, String, Text

from src.infrastructure.adapters.events.event_registry import serialize_event
from src.infrastructure.external.postgresql import Base

if TYPE_CHECKING:
    from src.domain.shared_kernel import DomainEvent


class OutboxMessageModel(Base):
    """One domain event awaiting delivery via Debezium CDC."""

    __tablename__ = "outbox"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    aggregatetype = Column(String, nullable=False)
    aggregateid = Column(String, nullable=False)
    type = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    occurred_at = Column(DateTime, nullable=False, default=datetime.now)

    @classmethod
    def from_domain_event(
        cls,
        event: "DomainEvent",
        aggregate_type: str,
        aggregate_id: str,
    ) -> "OutboxMessageModel":
        """Create an outbox row from a domain event."""
        return cls(
            id=event.event_id,
            aggregatetype=aggregate_type,
            aggregateid=aggregate_id,
            type=event.event_type,
            payload=serialize_event(event),
            occurred_at=event.occurred_at,
        )

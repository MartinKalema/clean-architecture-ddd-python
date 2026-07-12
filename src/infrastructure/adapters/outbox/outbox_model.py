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
replication slot has captured them. Retention is based on the database-owned
``inserted_at`` clock, never on the business event's ``occurred_at`` value.
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, Text, func

from src.infrastructure.adapters.events.event_registry import (
    outbox_type_for_event_class,
    serialize_event,
)
from src.infrastructure.external.postgresql import Base

if TYPE_CHECKING:
    from src.domain.shared_kernel import DomainEvent


class OutboxMessageModel(Base):
    """One domain event awaiting delivery via Debezium CDC."""

    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_inserted_at_id", "inserted_at", "id"),
        CheckConstraint(
            "id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_outbox_event_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "aggregatetype ~ '^[a-z][a-z0-9_-]{0,31}$'",
            name="ck_outbox_aggregate_type",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "aggregateid ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_outbox_aggregate_id",
        ).ddl_if(dialect="postgresql"),
    )

    id = Column(String(128), primary_key=True, default=lambda: str(uuid.uuid4()))
    aggregatetype = Column(String(32), nullable=False)
    aggregateid = Column(String(64), nullable=False)
    type = Column(String(160), nullable=False)
    payload = Column(Text, nullable=False)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    inserted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

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
            type=outbox_type_for_event_class(type(event)),
            payload=serialize_event(event),
            occurred_at=event.occurred_at,
        )

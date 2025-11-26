"""
Transactional Outbox Pattern Implementation.

The outbox pattern ensures reliable event publishing by storing events
in the same database transaction as the aggregate changes. A separate
worker then polls the outbox and publishes events to the message broker.

This guarantees at-least-once delivery even if the message broker is down.
"""
import json
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.shared_kernel import DomainEvent
from src.infrastructure.external.database import Base


class OutboxMessage(Base):
    """Stores domain events for reliable publishing."""
    __tablename__ = "outbox_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String, nullable=False, index=True)
    event_data = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)
    is_processed = Column(Boolean, default=False, nullable=False, index=True)
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    @classmethod
    def from_event(cls, event: DomainEvent) -> "OutboxMessage":
        """Create an outbox message from a domain event."""
        return cls(
            id=str(uuid.uuid4()),
            event_type=event.__class__.__name__,
            event_data=json.dumps(event.__dict__, default=str),
            created_at=datetime.utcnow()
        )

    def to_event_dict(self) -> dict:
        """Convert back to event data for dispatching."""
        return {
            "event_type": self.event_type,
            "payload": json.loads(self.event_data)
        }


class OutboxRepository:
    """Repository for managing outbox messages."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: DomainEvent) -> OutboxMessage:
        """Add a domain event to the outbox."""
        message = OutboxMessage.from_event(event)
        self.session.add(message)
        return message

    async def add_many(self, events: List[DomainEvent]) -> List[OutboxMessage]:
        """Add multiple domain events to the outbox."""
        messages = [OutboxMessage.from_event(event) for event in events]
        self.session.add_all(messages)
        return messages

    async def get_unprocessed(self, limit: int = 100) -> List[OutboxMessage]:
        """Get unprocessed messages for publishing."""
        result = await self.session.execute(
            select(OutboxMessage)
            .where(OutboxMessage.is_processed == False)
            .where(OutboxMessage.retry_count < 5)
            .order_by(OutboxMessage.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_as_processed(self, message_id: str) -> None:
        """Mark a message as successfully processed."""
        await self.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(is_processed=True, processed_at=datetime.utcnow())
        )

    async def mark_as_failed(self, message_id: str, error: str) -> None:
        """Mark a message as failed and increment retry count."""
        await self.session.execute(
            update(OutboxMessage)
            .where(OutboxMessage.id == message_id)
            .values(
                retry_count=OutboxMessage.retry_count + 1,
                error_message=error
            )
        )

"""Durable inbox and quarantine stores for event delivery."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, Protocol

from sqlalchemy import (
    Column,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.external.postgresql import Base


class InboxMessageModel(Base):
    """One handler's durable processing state for one event."""

    __tablename__ = "event_inbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'processed', 'failed')",
            name="ck_event_inbox_status",
        ),
        CheckConstraint("attempts >= 1", name="ck_event_inbox_attempts"),
        CheckConstraint(
            "contract_version >= 1", name="ck_event_inbox_contract_version"
        ),
        CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_event_inbox_payload_hash",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "event_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_event_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "handler_name ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_handler_name",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "contract_name ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_contract_name",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "correlation_id IS NULL OR correlation_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_correlation_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "causation_id IS NULL OR causation_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_event_inbox_causation_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "(status = 'processing' AND claim_token IS NOT NULL "
            "AND lease_until IS NOT NULL AND processed_at IS NULL) OR "
            "(status = 'processed' AND claim_token IS NULL "
            "AND lease_until IS NULL AND processed_at IS NOT NULL) OR "
            "(status = 'failed' AND claim_token IS NULL "
            "AND lease_until IS NULL AND processed_at IS NULL)",
            name="ck_event_inbox_status_fields",
        ),
        Index("ix_event_inbox_status_lease", "status", "lease_until"),
        Index("ix_event_inbox_processed_at", "processed_at"),
    )

    event_id = Column(String(128), primary_key=True)
    handler_name = Column(String(128), primary_key=True)
    contract_name = Column(String(160), nullable=False)
    contract_version = Column(Integer, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    correlation_id = Column(String(128), nullable=True)
    causation_id = Column(String(128), nullable=True)
    status = Column(String, nullable=False)
    attempts = Column(Integer, nullable=False, default=1, server_default="1")
    claim_token = Column(String, nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)


class QuarantinedEventModel(Base):
    """An unsupported or malformed event retained for operator action."""

    __tablename__ = "event_quarantine"
    __table_args__ = (
        CheckConstraint(
            "occurrence_count >= 1", name="ck_event_quarantine_occurrences"
        ),
        CheckConstraint(
            "id ~ '^[0-9a-f]{64}$'",
            name="ck_event_quarantine_id",
        ).ddl_if(dialect="postgresql"),
        Index("ix_event_quarantine_last_seen_at", "last_seen_at"),
    )

    id = Column(String(64), primary_key=True)
    event_id = Column(String(128), nullable=True, index=True)
    topic = Column(String(249), nullable=False)
    message_key = Column(Text, nullable=True)
    contract_name = Column(String(160), nullable=True)
    contract_version = Column(Integer, nullable=True)
    reason = Column(Text, nullable=False)
    payload = Column(Text, nullable=False)
    occurrence_count = Column(
        Integer, nullable=False, default=1, server_default="1"
    )
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)


class InboxClaimStatus(str, Enum):
    CLAIMED = "claimed"
    PROCESSED = "processed"
    BUSY = "busy"


@dataclass(frozen=True)
class InboxClaim:
    status: InboxClaimStatus
    token: str | None = None


class HandlerInbox(Protocol):
    async def claim(
        self,
        *,
        event_id: str,
        handler_name: str,
        contract_name: str,
        contract_version: int,
        payload_hash: str,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> InboxClaim: ...

    async def complete(
        self, *, event_id: str, handler_name: str, token: str
    ) -> None: ...

    async def fail(
        self,
        *,
        event_id: str,
        handler_name: str,
        token: str,
        error: Exception,
    ) -> None: ...


class EventQuarantine(Protocol):
    async def quarantine(
        self,
        *,
        topic: str,
        message_key: dict | str | None,
        payload: Any,
        reason: str,
        event_id: str | None,
        contract_name: str | None,
        contract_version: int | None,
    ) -> str: ...


class SqlAlchemyHandlerInbox:
    """Lease-based per-handler inbox safe for concurrent consumer instances."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        lease_seconds: int = 300,
    ) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        self._session_factory = session_factory
        self._lease = timedelta(seconds=lease_seconds)

    async def claim(
        self,
        *,
        event_id: str,
        handler_name: str,
        contract_name: str,
        contract_version: int,
        payload_hash: str,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> InboxClaim:
        if not _is_sha256(payload_hash):
            raise ValueError("payload_hash must be a lowercase SHA-256 digest")
        for field_name, value, max_length, optional in (
            ("event_id", event_id, 128, False),
            ("handler_name", handler_name, 128, False),
            ("contract_name", contract_name, 160, False),
            ("correlation_id", correlation_id, 128, True),
            ("causation_id", causation_id, 128, True),
        ):
            _validate_delivery_identity(
                value,
                field_name=field_name,
                max_length=max_length,
                optional=optional,
            )
        for _ in range(2):
            token = str(uuid.uuid4())
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        now = await _database_now(session)
                        row = await self._locked_row(session, event_id, handler_name)
                        if row is None:
                            session.add(
                                InboxMessageModel(
                                    event_id=event_id,
                                    handler_name=handler_name,
                                    contract_name=contract_name,
                                    contract_version=contract_version,
                                    payload_hash=payload_hash,
                                    correlation_id=correlation_id,
                                    causation_id=causation_id,
                                    status="processing",
                                    attempts=1,
                                    claim_token=token,
                                    lease_until=now + self._lease,
                                    received_at=now,
                                )
                            )
                            return InboxClaim(InboxClaimStatus.CLAIMED, token)

                        if (
                            row.contract_name != contract_name
                            or row.contract_version != contract_version
                            or row.payload_hash != payload_hash
                            or row.correlation_id != correlation_id
                            or row.causation_id != causation_id
                        ):
                            raise RuntimeError(
                                "Event identity collision for "
                                f"{event_id}/{handler_name}: stored contract or "
                                "trace metadata differs from this delivery"
                            )

                        if row.processed_at is not None or row.status == "processed":
                            return InboxClaim(InboxClaimStatus.PROCESSED)
                        if row.status == "processing" and _is_future(row.lease_until, now):
                            return InboxClaim(InboxClaimStatus.BUSY)

                        row.status = "processing"
                        row.attempts += 1
                        row.claim_token = token
                        row.lease_until = now + self._lease
                        row.last_error = None
                        return InboxClaim(InboxClaimStatus.CLAIMED, token)
            except IntegrityError:
                # Another consumer inserted the same composite key. Its row is
                # authoritative; retry once and observe processed/busy state.
                continue
        return InboxClaim(InboxClaimStatus.BUSY)

    async def complete(
        self, *, event_id: str, handler_name: str, token: str
    ) -> None:
        now = _utcnow()
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(InboxMessageModel)
                    .where(InboxMessageModel.event_id == event_id)
                    .where(InboxMessageModel.handler_name == handler_name)
                    .where(InboxMessageModel.claim_token == token)
                    .where(InboxMessageModel.processed_at.is_(None))
                    .values(
                        status="processed",
                        processed_at=now,
                        claim_token=None,
                        lease_until=None,
                        last_error=None,
                    )
                )
                if result.rowcount != 1:
                    raise RuntimeError(
                        f"Inbox claim was lost before completion: {event_id}/{handler_name}"
                    )

    async def fail(
        self,
        *,
        event_id: str,
        handler_name: str,
        token: str,
        error: Exception,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(InboxMessageModel)
                    .where(InboxMessageModel.event_id == event_id)
                    .where(InboxMessageModel.handler_name == handler_name)
                    .where(InboxMessageModel.claim_token == token)
                    .where(InboxMessageModel.processed_at.is_(None))
                    .values(
                        status="failed",
                        claim_token=None,
                        lease_until=None,
                        last_error=str(error)[:8_000],
                    )
                )
                if result.rowcount != 1:
                    raise RuntimeError(
                        f"Inbox claim was lost before failure was recorded: "
                        f"{event_id}/{handler_name}"
                    )

    @staticmethod
    async def _locked_row(
        session: AsyncSession, event_id: str, handler_name: str
    ) -> Optional[InboxMessageModel]:
        result = await session.execute(
            select(InboxMessageModel)
            .where(InboxMessageModel.event_id == event_id)
            .where(InboxMessageModel.handler_name == handler_name)
            .with_for_update()
        )
        return result.scalar_one_or_none()


class SqlAlchemyEventQuarantine:
    """Durably retain bad contracts instead of acknowledging and losing them."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        self._session_factory = session_factory

    async def quarantine(
        self,
        *,
        topic: str,
        message_key: dict | str | None,
        payload: Any,
        reason: str,
        event_id: str | None,
        contract_name: str | None,
        contract_version: int | None,
    ) -> str:
        if not isinstance(topic, str) or not 1 <= len(topic) <= 249:
            raise ValueError("Kafka topic must be between 1 and 249 characters")
        event_id = _searchable_identity(event_id, max_length=128)
        contract_name = _searchable_identity(contract_name, max_length=160)
        payload_json = _canonical_json(payload)
        key_json = None if message_key is None else _canonical_json(message_key)
        fingerprint = hashlib.sha256(
            f"{topic}\0{key_json}\0{payload_json}".encode("utf-8")
        ).hexdigest()

        for _ in range(2):
            now = _utcnow()
            try:
                async with self._session_factory() as session:
                    async with session.begin():
                        row = await session.get(
                            QuarantinedEventModel,
                            fingerprint,
                            with_for_update=True,
                        )
                        if row is None:
                            session.add(
                                QuarantinedEventModel(
                                    id=fingerprint,
                                    event_id=event_id,
                                    topic=topic,
                                    message_key=key_json,
                                    contract_name=contract_name,
                                    contract_version=contract_version,
                                    reason=reason,
                                    payload=payload_json,
                                    occurrence_count=1,
                                    first_seen_at=now,
                                    last_seen_at=now,
                                )
                            )
                        else:
                            row.occurrence_count += 1
                            row.last_seen_at = now
                            row.reason = reason
                        return fingerprint
            except IntegrityError:
                continue
        raise RuntimeError(f"Could not persist quarantined event {fingerprint}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _database_now(session: AsyncSession) -> datetime:
    """Use the database clock so lease ownership ignores worker clock skew."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return _utcnow()
    value = await session.scalar(select(func.clock_timestamp()))
    if not isinstance(value, datetime):
        raise RuntimeError("Database did not return a lease timestamp")
    return value


def _is_future(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        return value > now.replace(tzinfo=None)
    return value > now


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    except (TypeError, ValueError) as error:
        return json.dumps(
            {"unserializable_payload": repr(value), "serialization_error": str(error)},
            sort_keys=True,
            separators=(",", ":"),
        )


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_delivery_identity(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
    optional: bool,
) -> None:
    if value is None and optional:
        return
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= max_length
        or not value[0].isalnum()
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:-"
            for character in value
        )
    ):
        raise ValueError(f"{field_name} has an invalid event-delivery identity")


def _searchable_identity(value: str | None, *, max_length: int) -> str | None:
    """Keep a bounded searchable hint; the full malformed value stays in payload."""
    if value is None:
        return None
    try:
        _validate_delivery_identity(
            value,
            field_name="quarantine identity",
            max_length=max_length,
            optional=True,
        )
    except ValueError:
        return None
    return value

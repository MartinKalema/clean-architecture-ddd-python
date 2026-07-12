"""Persistence models for application workflow state (not domain aggregates)."""
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text, func

from src.infrastructure.external.postgresql import Base


class CommandReceiptModel(Base):
    __tablename__ = "command_receipts"
    __table_args__ = (
        Index("ix_command_receipts_created_at", "created_at"),
        CheckConstraint(
            "length(scope) BETWEEN 1 AND 64", name="ck_command_receipts_scope"
        ),
        CheckConstraint(
            "length(idempotency_key) BETWEEN 8 AND 128 AND "
            "idempotency_key ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_command_receipts_key",
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'", name="ck_command_receipts_hash"
        ),
    )

    scope = Column(String(64), primary_key=True)
    idempotency_key = Column(String(128), primary_key=True)
    request_hash = Column(String(64), nullable=False)
    response_payload = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BorrowOperationModel(Base):
    __tablename__ = "borrow_operations"
    __table_args__ = (
        Index("ix_borrow_operations_book_id", "book_id"),
        Index("ix_borrow_operations_status_updated", "status", "updated_at"),
        CheckConstraint(
            "status IN ('reserved', 'borrowed', 'released', 'returned')",
            name="ck_borrow_operations_status",
        ),
        CheckConstraint(
            "reservation_generation >= 1", name="ck_borrow_operations_generation"
        ),
        CheckConstraint(
            "updated_at >= created_at", name="ck_borrow_operations_timestamps"
        ),
        CheckConstraint(
            "operation_id ~* "
            "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_borrow_operations_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "book_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_borrow_operations_book_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "patron_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_borrow_operations_patron_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "loan_id IS NULL OR loan_id ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
            name="ck_borrow_operations_loan_id",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "(status = 'reserved' AND loan_id IS NULL AND failure_reason IS NULL) OR "
            "(status = 'borrowed' AND loan_id IS NOT NULL AND failure_reason IS NULL) OR "
            "(status = 'returned' AND loan_id IS NOT NULL AND failure_reason IS NULL) OR "
            "(status = 'released' AND loan_id IS NULL AND "
            "failure_reason IS NOT NULL AND "
            "length(trim(failure_reason)) BETWEEN 1 AND 500)",
            name="ck_borrow_operations_state",
        ),
    )

    operation_id = Column(String(36), primary_key=True)
    book_id = Column(String(64), nullable=False)
    patron_id = Column(String(64), nullable=False)
    reservation_generation = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    loan_id = Column(String(64), nullable=True)
    failure_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class MigrationSafetyMarkerModel(Base):
    """Durable proof that a historically destructive migration was audited."""

    __tablename__ = "migration_safety_markers"

    name = Column(String(128), primary_key=True)
    value = Column(String(128), nullable=False)
    recorded_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LegacyEventMigrationAuditModel(Base):
    """Finite audit of polling events compensated during revision 004."""

    __tablename__ = "legacy_event_migration_audit"
    __table_args__ = (
        CheckConstraint(
            "length(event_type) BETWEEN 1 AND 64",
            name="ck_legacy_event_audit_type",
        ),
        CheckConstraint(
            "length(aggregate_type) BETWEEN 1 AND 32",
            name="ck_legacy_event_audit_aggregate_type",
        ),
        CheckConstraint(
            "length(aggregate_id) BETWEEN 1 AND 64",
            name="ck_legacy_event_audit_aggregate_id",
        ),
        CheckConstraint(
            "length(reason) BETWEEN 1 AND 500",
            name="ck_legacy_event_audit_reason",
        ),
    )

    event_id = Column(String(128), primary_key=True)
    event_type = Column(String(64), nullable=False)
    aggregate_type = Column(String(32), nullable=False)
    aggregate_id = Column(String(64), nullable=False)
    reason = Column(String(500), nullable=False)
    recorded_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

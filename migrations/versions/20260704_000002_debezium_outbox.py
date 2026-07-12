"""Replace polling outbox with Debezium outbox table.

The old outbox_messages table supported a polling publisher (worker marked
rows processed and retried failures). The new outbox table is append-only
and shaped for the Debezium Outbox Event Router, which tails the WAL and
routes each row to the Kafka topic outbox.event.<aggregatetype>.

Revision ID: 002
Revises: 001
Create Date: 2026-07-04

Pending polling-outbox rows are converted before the legacy table is removed;
the migration aborts transactionally if any row cannot be mapped safely. The
configured legacy timezone resolves naive payload values; migrated SQL clocks
are stored UTC-naive with explicit payload provenance until revision 005
changes the column to timezone-aware storage.

Deployments that ran an older copy of revision 002 may already contain that
ambiguous mixture. A later revision cannot distinguish which naive values were
previously normalized to UTC; those installations require an operator audit or
recovery from backup/WAL before revision 005 converts the column.
"""
import json
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from migrations.legacy_naive_time import (
    localize_unambiguous_legacy_datetime,
    require_legacy_naive_timezone,
)


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # OUTBOX table (Debezium Outbox Event Router column names)
    op.create_table(
        'outbox',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('aggregatetype', sa.String(), nullable=False),
        sa.Column('aggregateid', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    _migrate_pending_polling_rows(op.get_bind())

    op.create_table(
        "migration_safety_markers",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("value", sa.String(128), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("name"),
    )
    op.get_bind().execute(
        sa.text(
            "INSERT INTO migration_safety_markers (name, value) "
            "VALUES (:name, :value)"
        ),
        {
            "name": "revision-002-lossless-outbox",
            "value": "locked-copy-and-explicit-timezone-v2",
        },
    )

    op.drop_index('ix_outbox_messages_is_processed_created_at', table_name='outbox_messages')
    op.drop_index(op.f('ix_outbox_messages_is_processed'), table_name='outbox_messages')
    op.drop_index(op.f('ix_outbox_messages_event_type'), table_name='outbox_messages')
    op.drop_table('outbox_messages')


def downgrade() -> None:
    connection = op.get_bind()
    retained_rows = connection.scalar(sa.text("SELECT count(*) FROM outbox"))
    if retained_rows:
        raise RuntimeError(
            "Cannot downgrade migration 002 while Debezium outbox rows exist: "
            "delivery state cannot be reconstructed as polling acknowledgements. "
            "Restore a pre-002 backup instead."
        )

    op.create_table(
        'outbox_messages',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('event_data', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('is_processed', sa.Boolean(), nullable=False, default=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_outbox_messages_event_type'), 'outbox_messages', ['event_type'], unique=False)
    op.create_index(op.f('ix_outbox_messages_is_processed'), 'outbox_messages', ['is_processed'], unique=False)
    op.create_index('ix_outbox_messages_is_processed_created_at', 'outbox_messages', ['is_processed', 'created_at'], unique=False)

    op.drop_table('outbox')
    op.execute("DROP TABLE IF EXISTS migration_safety_markers")


_AGGREGATE_BY_EVENT = {
    "BookAddedToCatalog": ("book", "book_id"),
    "BookRemovedFromCatalog": ("book", "book_id"),
    "CatalogBookReserved": ("book", "book_id"),
    "CatalogBookBorrowed": ("book", "book_id"),
    "CatalogBookReleased": ("book", "book_id"),
    "CatalogBookReturned": ("book", "book_id"),
    "LoanCreated": ("loan", "loan_id"),
    "LoanCompleted": ("loan", "loan_id"),
    "LoanCancelled": ("loan", "loan_id"),
    "LoanExtended": ("loan", "loan_id"),
    "BookOverdue": ("loan", "loan_id"),
    "PatronRegistered": ("patron", "patron_id"),
    "PatronSuspended": ("patron", "patron_id"),
    "PatronReinstated": ("patron", "patron_id"),
}
_BATCH_SIZE = 500
_LEGACY_DATETIME_FIELDS = {
    "BookAddedToCatalog": ("occurred_at",),
    "BookRemovedFromCatalog": ("occurred_at",),
    "CatalogBookReserved": (
        "occurred_at",
        "reserved_at",
        "return_due_date",
    ),
    "CatalogBookBorrowed": (
        "occurred_at",
        "borrowed_at",
        "return_due_date",
    ),
    "CatalogBookReleased": ("occurred_at",),
    "CatalogBookReturned": ("occurred_at",),
    "LoanCreated": ("occurred_at", "borrowed_at", "due_date"),
    "LoanCompleted": ("occurred_at", "returned_at"),
    "LoanCancelled": ("occurred_at",),
    "LoanExtended": ("occurred_at", "old_due_date", "new_due_date"),
    "BookOverdue": ("occurred_at", "due_date"),
    "PatronRegistered": ("occurred_at",),
    "PatronSuspended": ("occurred_at",),
    "PatronReinstated": ("occurred_at",),
}


def _migrate_pending_polling_rows(connection) -> None:
    """Copy every unacknowledged legacy row using bounded keyset batches."""
    # Fence both the polling publisher and legacy application writers for the
    # complete copy/drop transaction.  Without this lock, a transaction could
    # insert after the final keyset read and commit immediately before DROP,
    # silently losing an unacknowledged event.
    connection.execute(
        sa.text("LOCK TABLE outbox_messages IN ACCESS EXCLUSIVE MODE")
    )
    last_id = None
    legacy_timezone = None
    query = sa.text(
        """
        SELECT id, event_type, event_data, created_at, retry_count, error_message
          FROM outbox_messages
         WHERE is_processed = false
           AND (:last_id IS NULL OR id > :last_id)
         ORDER BY id
         LIMIT :batch_size
        """
    ).bindparams(
        sa.bindparam("last_id", type_=sa.String()),
        sa.bindparam("batch_size", type_=sa.Integer()),
    )
    insert_row = sa.text(
        """
        INSERT INTO outbox
            (id, aggregatetype, aggregateid, type, payload, occurred_at)
        VALUES
            (:id, :aggregatetype, :aggregateid, :type, :payload, :occurred_at)
        """
    )

    while True:
        rows = connection.execute(
            query, {"last_id": last_id, "batch_size": _BATCH_SIZE}
        ).mappings().all()
        if not rows:
            return
        if legacy_timezone is None:
            legacy_timezone = require_legacy_naive_timezone(
                has_legacy_timestamps=True,
                revision=revision,
            )
        converted = [
            _convert_legacy_row(row, legacy_timezone=legacy_timezone)
            for row in rows
        ]
        connection.execute(insert_row, converted)
        last_id = rows[-1]["id"]


def _convert_legacy_row(row, *, legacy_timezone: str) -> dict:
    event_type = row["event_type"]
    mapping = _AGGREGATE_BY_EVENT.get(event_type)
    if mapping is None:
        raise RuntimeError(
            f"Cannot migrate pending outbox row {row['id']}: "
            f"unknown event type {event_type!r}"
        )
    try:
        event_data = json.loads(row["event_data"])
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Cannot migrate pending outbox row {row['id']}: invalid JSON"
        ) from error
    if not isinstance(event_data, dict):
        raise RuntimeError(
            f"Cannot migrate pending outbox row {row['id']}: event_data is not an object"
        )

    aggregate_type, id_field = mapping
    aggregate_id = event_data.get(id_field)
    if not isinstance(aggregate_id, str) or not aggregate_id:
        raise RuntimeError(
            f"Cannot migrate pending outbox row {row['id']}: "
            f"missing {id_field}"
        )

    event_data = _normalize_legacy_payload_datetimes(
        event_data,
        event_type=event_type,
        fallback_occurred_at=row["created_at"],
        row_id=row["id"],
        legacy_timezone=legacy_timezone,
    )
    event_data["event_type"] = event_type
    event_data["_legacy_delivery"] = {
        "retry_count": row["retry_count"],
        "last_error": row["error_message"],
        # The SQL column is timestamp-without-time-zone until revision 005.
        # Store a UTC-naive value and mark that provenance so 005 can recover
        # the exact instant even during a repeated DST hour.
        "occurred_at_storage": "utc-naive",
    }
    return {
        "id": row["id"],
        "aggregatetype": aggregate_type,
        "aggregateid": aggregate_id,
        "type": event_type,
        "payload": json.dumps(event_data, separators=(",", ":"), default=str),
        "occurred_at": _legacy_occurred_at(
            event_data.get("occurred_at"),
            fallback=row["created_at"],
            row_id=row["id"],
            legacy_timezone=legacy_timezone,
        ),
    }


def _normalize_legacy_payload_datetimes(
    event_data: dict,
    *,
    event_type: str,
    fallback_occurred_at,
    row_id: str,
    legacy_timezone: str,
) -> dict:
    """Write every recognized event datetime with an explicit UTC offset."""
    result = dict(event_data)
    for field_name in _LEGACY_DATETIME_FIELDS[event_type]:
        value = result.get(field_name)
        if field_name == "occurred_at" and value is None:
            value = fallback_occurred_at
        if value is None:
            continue
        result[field_name] = _legacy_datetime_as_utc(
            value,
            row_id=row_id,
            field_name=field_name,
            legacy_timezone=legacy_timezone,
        ).isoformat()
    return result


def _legacy_datetime_as_utc(
    value,
    *,
    row_id: str,
    field_name: str,
    legacy_timezone: str,
) -> datetime:
    if isinstance(value, str):
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            value = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise RuntimeError(
                f"Cannot migrate pending outbox row {row_id}: invalid "
                f"{field_name}"
            ) from error
    if not isinstance(value, datetime):
        raise RuntimeError(
            f"Cannot migrate pending outbox row {row_id}: invalid {field_name}"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        value = _attach_unambiguous_legacy_timezone(
            value,
            row_id=row_id,
            field_name=field_name,
            legacy_timezone=legacy_timezone,
        )
    return value.astimezone(timezone.utc)


def _attach_unambiguous_legacy_timezone(
    value: datetime,
    *,
    row_id: str,
    field_name: str,
    legacy_timezone: str,
) -> datetime:
    """Reject wall times whose UTC instant cannot be reconstructed exactly."""
    return localize_unambiguous_legacy_datetime(
        value,
        timezone_name=legacy_timezone,
        location=f"pending outbox row {row_id}: {field_name}",
    )


def _legacy_occurred_at(
    value,
    *,
    fallback,
    row_id: str,
    legacy_timezone: str,
) -> datetime:
    """Return a UTC-naive value with explicit provenance in the payload."""
    candidate = fallback if value is None else value
    if isinstance(candidate, str):
        normalized = (
            candidate[:-1] + "+00:00"
            if candidate.endswith("Z")
            else candidate
        )
        try:
            candidate = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise RuntimeError(
                f"Cannot migrate pending outbox row {row_id}: "
                "invalid occurred_at"
            ) from error
    if not isinstance(candidate, datetime):
        raise RuntimeError(
            f"Cannot migrate pending outbox row {row_id}: invalid occurred_at"
        )
    if candidate.tzinfo is None or candidate.utcoffset() is None:
        candidate = localize_unambiguous_legacy_datetime(
            candidate,
            timezone_name=legacy_timezone,
            location=f"pending outbox row {row_id}: occurred_at",
        )
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)

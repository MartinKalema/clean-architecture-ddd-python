"""Bound identifiers used by outbox routing and event-delivery indexes.

Revision ID: 009
Revises: 008
Create Date: 2026-07-11
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    invalid = connection.execute(
        sa.text(
            """
            SELECT
                count(*) FILTER (WHERE
                    length(id) NOT BETWEEN 1 AND 128 OR
                    id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' OR
                    length(aggregatetype) NOT BETWEEN 1 AND 32 OR
                    aggregatetype !~ '^[a-z][a-z0-9_-]{0,31}$' OR
                    length(aggregateid) NOT BETWEEN 1 AND 64 OR
                    aggregateid !~ '^[A-Za-z0-9][A-Za-z0-9_-]*$' OR
                    length(type) NOT BETWEEN 1 AND 160
                ) AS invalid_outbox,
                (SELECT count(*) FROM event_inbox WHERE
                    length(event_id) NOT BETWEEN 1 AND 128 OR
                    event_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' OR
                    length(handler_name) NOT BETWEEN 1 AND 128 OR
                    handler_name !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' OR
                    length(contract_name) NOT BETWEEN 1 AND 160 OR
                    contract_name !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' OR
                    (correlation_id IS NOT NULL AND (
                        length(correlation_id) NOT BETWEEN 1 AND 128 OR
                        correlation_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$')) OR
                    (causation_id IS NOT NULL AND (
                        length(causation_id) NOT BETWEEN 1 AND 128 OR
                        causation_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'))
                ) AS invalid_inbox,
                (SELECT count(*) FROM event_quarantine WHERE
                    length(id) <> 64 OR
                    id !~ '^[0-9a-f]{64}$' OR
                    (event_id IS NOT NULL AND length(event_id) > 128) OR
                    length(topic) NOT BETWEEN 1 AND 249 OR
                    (contract_name IS NOT NULL AND length(contract_name) > 160)
                ) AS invalid_quarantine
              FROM outbox
            """
        )
    ).mappings().one()
    if any(invalid.values()):
        raise RuntimeError(
            "Migration 009 found unbounded event delivery identifiers: "
            f"outbox={invalid['invalid_outbox']}, "
            f"inbox={invalid['invalid_inbox']}, "
            f"quarantine={invalid['invalid_quarantine']}. Reconcile the "
            "reported durable records before retrying."
        )

    for table, column, size in (
        ("outbox", "id", 128),
        ("outbox", "aggregatetype", 32),
        ("outbox", "aggregateid", 64),
        ("outbox", "type", 160),
        ("event_inbox", "event_id", 128),
        ("event_inbox", "handler_name", 128),
        ("event_inbox", "contract_name", 160),
        ("event_inbox", "correlation_id", 128),
        ("event_inbox", "causation_id", 128),
        ("event_quarantine", "id", 64),
        ("event_quarantine", "event_id", 128),
        ("event_quarantine", "topic", 249),
        ("event_quarantine", "contract_name", 160),
    ):
        op.alter_column(
            table,
            column,
            existing_type=sa.String(),
            type_=sa.String(size),
        )

    op.create_check_constraint(
        "ck_outbox_event_id",
        "outbox",
        "id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
    )
    op.create_check_constraint(
        "ck_outbox_aggregate_type",
        "outbox",
        "aggregatetype ~ '^[a-z][a-z0-9_-]{0,31}$'",
    )
    op.create_check_constraint(
        "ck_outbox_aggregate_id",
        "outbox",
        "aggregateid ~ '^[A-Za-z0-9][A-Za-z0-9_-]*$'",
    )
    for name, expression in (
        ("event_id", "event_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"),
        ("handler_name", "handler_name ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"),
        ("contract_name", "contract_name ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"),
        (
            "correlation_id",
            "correlation_id IS NULL OR correlation_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
        ),
        (
            "causation_id",
            "causation_id IS NULL OR causation_id ~ "
            "'^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
        ),
    ):
        op.create_check_constraint(
            f"ck_event_inbox_{name}", "event_inbox", expression
        )
    op.create_check_constraint(
        "ck_event_quarantine_id",
        "event_quarantine",
        "id ~ '^[0-9a-f]{64}$'",
    )


def downgrade() -> None:
    for constraint, table in (
        ("ck_event_quarantine_id", "event_quarantine"),
        ("ck_event_inbox_causation_id", "event_inbox"),
        ("ck_event_inbox_correlation_id", "event_inbox"),
        ("ck_event_inbox_contract_name", "event_inbox"),
        ("ck_event_inbox_handler_name", "event_inbox"),
        ("ck_event_inbox_event_id", "event_inbox"),
        ("ck_outbox_aggregate_id", "outbox"),
        ("ck_outbox_aggregate_type", "outbox"),
        ("ck_outbox_event_id", "outbox"),
    ):
        op.drop_constraint(constraint, table, type_="check")

    for table, column in (
        ("event_quarantine", "contract_name"),
        ("event_quarantine", "topic"),
        ("event_quarantine", "event_id"),
        ("event_quarantine", "id"),
        ("event_inbox", "causation_id"),
        ("event_inbox", "correlation_id"),
        ("event_inbox", "contract_name"),
        ("event_inbox", "handler_name"),
        ("event_inbox", "event_id"),
        ("outbox", "type"),
        ("outbox", "aggregateid"),
        ("outbox", "aggregatetype"),
        ("outbox", "id"),
    ):
        op.alter_column(
            table,
            column,
            existing_type=sa.String(),
            type_=sa.String(),
        )

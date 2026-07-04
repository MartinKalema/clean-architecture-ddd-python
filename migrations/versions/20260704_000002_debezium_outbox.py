"""Replace polling outbox with Debezium outbox table

The old outbox_messages table supported a polling publisher (worker marked
rows processed and retried failures). The new outbox table is append-only
and shaped for the Debezium Outbox Event Router, which tails the WAL and
routes each row to the Kafka topic outbox.event.<aggregatetype>.

Revision ID: 002
Revises: 001
Create Date: 2026-07-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Old polling-outbox table (code removed in 0.2.0)
    op.drop_index('ix_outbox_messages_is_processed_created_at', table_name='outbox_messages')
    op.drop_index(op.f('ix_outbox_messages_is_processed'), table_name='outbox_messages')
    op.drop_index(op.f('ix_outbox_messages_event_type'), table_name='outbox_messages')
    op.drop_table('outbox_messages')

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


def downgrade() -> None:
    op.drop_table('outbox')

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

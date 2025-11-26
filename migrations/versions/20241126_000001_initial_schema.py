"""Initial schema with books and outbox tables

Revision ID: 001
Revises:
Create Date: 2024-11-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create books table
    op.create_table(
        'books',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('author', sa.String(), nullable=True),
        sa.Column('is_borrowed', sa.Boolean(), nullable=True, default=False),
        sa.Column('borrowed_at', sa.DateTime(), nullable=True),
        sa.Column('return_due_date', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, default=0),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_books_id'), 'books', ['id'], unique=False)
    op.create_index(op.f('ix_books_title'), 'books', ['title'], unique=False)

    # Create outbox_messages table for transactional outbox pattern
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


def downgrade() -> None:
    op.drop_index(op.f('ix_outbox_messages_is_processed'), table_name='outbox_messages')
    op.drop_index(op.f('ix_outbox_messages_event_type'), table_name='outbox_messages')
    op.drop_table('outbox_messages')

    op.drop_index(op.f('ix_books_title'), table_name='books')
    op.drop_index(op.f('ix_books_id'), table_name='books')
    op.drop_table('books')

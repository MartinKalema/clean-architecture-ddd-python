"""Replace books.is_borrowed with a status state machine

The borrow saga needs a semantic lock: RESERVED marks a book whose borrow
committed but whose loan is not yet confirmed. A boolean cannot represent
that tentative state, so is_borrowed becomes status
(available/reserved/borrowed) plus reserved_at for reservation expiry.

Revision ID: 003
Revises: 002
Create Date: 2026-07-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('books', sa.Column('status', sa.String(), nullable=False, server_default='available'))
    op.add_column('books', sa.Column('reserved_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE books SET status = 'borrowed' WHERE is_borrowed = true")
    op.drop_index(op.f('ix_books_is_borrowed'), table_name='books')
    op.drop_column('books', 'is_borrowed')
    op.create_index(op.f('ix_books_status'), 'books', ['status'], unique=False)
    # Reaper scan: reserved books ordered by reservation age
    op.create_index('ix_books_status_reserved_at', 'books', ['status', 'reserved_at'], unique=False)


def downgrade() -> None:
    op.add_column('books', sa.Column('is_borrowed', sa.Boolean(), nullable=True, server_default='false'))
    op.execute("UPDATE books SET is_borrowed = (status != 'available')")
    op.drop_index('ix_books_status_reserved_at', table_name='books')
    op.drop_index(op.f('ix_books_status'), table_name='books')
    op.drop_column('books', 'reserved_at')
    op.drop_column('books', 'status')
    op.create_index(op.f('ix_books_is_borrowed'), 'books', ['is_borrowed'], unique=False)

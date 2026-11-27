"""feedback: read / unread mark for the back office

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-27 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('feedback', sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.create_index('ix_feedback_created_at', 'feedback', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_feedback_created_at', table_name='feedback')
    op.drop_column('feedback', 'is_read')

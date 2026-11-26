"""halving bookkeeping columns on topics

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26 16:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('topics', sa.Column('state_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('topics', sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('topics', sa.Column('votes_at_eval', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('topics', 'votes_at_eval')
    op.drop_column('topics', 'evaluated_at')
    op.drop_column('topics', 'state_changed_at')

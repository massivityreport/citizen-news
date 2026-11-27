"""feedback_replies: replies e-mailed by the admin to the author of an opinion

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-27 19:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'feedback_replies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feedback_id', sa.Integer(), sa.ForeignKey('feedback.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
    )
    op.create_index('ix_feedback_replies_feedback_id', 'feedback_replies', ['feedback_id'])


def downgrade() -> None:
    op.drop_index('ix_feedback_replies_feedback_id', table_name='feedback_replies')
    op.drop_table('feedback_replies')

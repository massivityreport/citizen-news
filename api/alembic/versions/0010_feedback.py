"""feedback sent from the public site

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-27 16:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('page_name', sa.String(length=200), nullable=False),
    sa.Column('page_url', sa.String(length=500), nullable=False),
    sa.Column('screen', sa.String(length=20), nullable=False),
    sa.Column('browser', sa.String(length=300), nullable=False),
    sa.Column('recent_actions', sa.JSON(), nullable=True),
    sa.CheckConstraint("kind IN ('problem', 'idea', 'other')", name=op.f('ck_feedback_kind')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_feedback'))
    )


def downgrade() -> None:
    op.drop_table('feedback')

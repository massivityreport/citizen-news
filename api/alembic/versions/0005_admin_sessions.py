"""admin sessions

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('admin_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_admin_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_admin_sessions_token_hash'))
    )


def downgrade() -> None:
    op.drop_table('admin_sessions')

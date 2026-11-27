"""media source admin: active flag and permanently deleted sources

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-26 19:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('media_sources', sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.create_table('deleted_sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feed_url', sa.Text(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deleted_sources')),
    sa.UniqueConstraint('feed_url', name=op.f('uq_deleted_sources_feed_url'))
    )


def downgrade() -> None:
    op.drop_table('deleted_sources')
    op.drop_column('media_sources', 'active')

"""articles.image_url: hotlinked image URL (https only, never downloaded)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('image_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('articles', 'image_url')

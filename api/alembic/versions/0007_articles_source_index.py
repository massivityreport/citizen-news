"""index on articles.source_id (back-office filter by source, cascade when a source is deleted)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-27 09:00:00
"""
from alembic import op


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_articles_source_id', 'articles', ['source_id'])


def downgrade() -> None:
    op.drop_index('ix_articles_source_id', table_name='articles')

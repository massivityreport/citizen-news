"""indexes on articles.fetched_at and votes.created_at (back-office statistics: 24 h window and 30-day curves)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-27 12:00:00
"""
from alembic import op


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_articles_fetched_at', 'articles', ['fetched_at'])
    op.create_index('ix_votes_created_at', 'votes', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_votes_created_at', table_name='votes')
    op.drop_index('ix_articles_fetched_at', table_name='articles')

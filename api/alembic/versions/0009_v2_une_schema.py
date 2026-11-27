"""V2 schema: citizens compose a une of 10 topics; replaces the V1 votes and halving.

IRREVERSIBLE FOR THE DATA. upgrade() drops the `votes` table and the topic columns `state`, `wave`,
`state_changed_at`, `evaluated_at`, `votes_at_eval`: every vote and every halving state is lost (decision
of the product owner: net replacement of V1). downgrade() only recreates the EMPTY structures (an empty
`votes` table, the topic columns with their defaults: state 'new', wave 0, votes_at_eval 0) so that the
V1 code could start again; it cannot bring the data back, and it drops the V2 tables with their content
(selections, editions, edition_topics, login_tokens.draft).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-27 14:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- V1 removal (data loss) ---
    op.drop_index('ix_votes_created_at', table_name='votes')
    op.drop_index('ix_votes_topic_id', table_name='votes')
    op.drop_table('votes')
    op.drop_index('ix_topics_state', table_name='topics')
    op.drop_constraint(op.f('ck_topics_state'), 'topics', type_='check')
    for column in ('votes_at_eval', 'evaluated_at', 'state_changed_at', 'wave', 'state'):
        op.drop_column('topics', column)

    # --- V2 ---
    op.create_table('selections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('edition_date', sa.Date(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_selections_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_selections_topic_id_topics'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_selections')),
    sa.UniqueConstraint('account_id', 'edition_date', 'topic_id', name='uq_selections_account_id_edition_date_topic_id')
    )
    op.create_index('ix_selections_edition_date_topic_id', 'selections', ['edition_date', 'topic_id'], unique=False)
    op.create_table('editions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edition_date', sa.Date(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('participants', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_editions')),
    sa.UniqueConstraint('edition_date', name=op.f('uq_editions_edition_date'))
    )
    op.create_table('edition_topics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edition_id', sa.Integer(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('sources', sa.JSON(), nullable=False),
    sa.Column('source_count', sa.Integer(), nullable=False),
    sa.Column('article_count', sa.Integer(), nullable=False),
    sa.Column('approvals', sa.Integer(), nullable=False),
    sa.Column('proportion', sa.Float(), nullable=False),
    sa.Column('image_url', sa.String(length=500), nullable=True),
    sa.CheckConstraint('rank BETWEEN 1 AND 10', name=op.f('ck_edition_topics_rank')),
    sa.ForeignKeyConstraint(['edition_id'], ['editions.id'], name=op.f('fk_edition_topics_edition_id_editions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_edition_topics_topic_id_topics'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_edition_topics')),
    sa.UniqueConstraint('edition_id', 'rank', name='uq_edition_topics_edition_id_rank')
    )
    op.add_column('login_tokens', sa.Column('draft', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('login_tokens', 'draft')
    op.drop_table('edition_topics')
    op.drop_table('editions')
    op.drop_index('ix_selections_edition_date_topic_id', table_name='selections')
    op.drop_table('selections')

    # Empty V1 structures (the data is gone for good, see the header).
    op.add_column('topics', sa.Column('state', sa.String(length=16), server_default='new', nullable=False))
    op.add_column('topics', sa.Column('wave', sa.Integer(), server_default='0', nullable=False))
    op.add_column('topics', sa.Column('state_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('topics', sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('topics', sa.Column('votes_at_eval', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint(op.f('ck_topics_state'), 'topics', "state IN ('new', 'active', 'reserve', 'emerged')")
    op.create_index('ix_topics_state', 'topics', ['state'], unique=False)
    op.create_table('votes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('choice', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("choice IN ('more', 'not_priority', 'unknown')", name=op.f('ck_votes_choice')),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name=op.f('fk_votes_account_id_accounts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_votes_topic_id_topics'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_votes')),
    sa.UniqueConstraint('account_id', 'topic_id', name='uq_votes_account_id_topic_id')
    )
    op.create_index('ix_votes_topic_id', 'votes', ['topic_id'], unique=False)
    op.create_index('ix_votes_created_at', 'votes', ['created_at'], unique=False)

"""Migration 0009 (V1 -> V2 schema) on a populated database. Uses the test database: goes back to 0008,
fills it as V1 would have, upgrades, checks, downgrades, and always ends at head."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.db import get_engine

CFG = Config("alembic.ini")
V2_TABLES = {"selections", "editions", "edition_topics"}


def _columns(table):
    return {c["name"] for c in inspect(get_engine()).get_columns(table)}


@pytest.fixture
def at_0008(session):
    session.rollback()
    session.close()
    command.downgrade(CFG, "0008")
    yield
    command.upgrade(CFG, "head")


def _populate_v1():
    with get_engine().begin() as c:
        c.execute(text("INSERT INTO media_sources (name, feed_url) VALUES ('M', 'https://m.example/rss')"))
        c.execute(text("INSERT INTO topics (title, state, wave, votes_at_eval) VALUES ('Sujet A', 'emerged', 2, 5), ('Sujet B', 'new', 0, 0)"))
        c.execute(text("INSERT INTO articles (source_id, url, title, topic_id) VALUES (1, 'https://m.example/1', 'Art', 1)"))
        c.execute(text("INSERT INTO accounts (email) VALUES ('a@example.org')"))
        c.execute(text("INSERT INTO sessions (account_id, token_hash, expires_at) VALUES (1, 'h', now() + interval '1 day')"))
        c.execute(text("INSERT INTO votes (account_id, topic_id, choice) VALUES (1, 1, 'more'), (1, 2, 'unknown')"))
        c.execute(text("INSERT INTO login_tokens (email, token_hash, expires_at) VALUES ('a@example.org', 't', now() + interval '1 day')"))


def test_upgrade_keeps_content_and_drops_v1(at_0008):
    _populate_v1()
    command.upgrade(CFG, "0009")
    engine = get_engine()
    tables = set(inspect(engine).get_table_names())
    assert "votes" not in tables and V2_TABLES <= tables
    assert not {"state", "wave", "state_changed_at", "evaluated_at", "votes_at_eval"} & _columns("topics")
    assert "draft" in _columns("login_tokens")
    with engine.connect() as c:
        assert [r[0] for r in c.execute(text("SELECT title FROM topics ORDER BY id"))] == ["Sujet A", "Sujet B"]
        assert c.scalar(text("SELECT count(*) FROM accounts")) == 1
        assert c.scalar(text("SELECT count(*) FROM sessions")) == 1
        assert c.scalar(text("SELECT count(*) FROM articles WHERE topic_id = 1")) == 1
        assert c.scalar(text("SELECT draft FROM login_tokens")) is None
    # The V1 index and check constraint went away with their columns.
    assert "ix_topics_state" not in {i["name"] for i in inspect(engine).get_indexes("topics")}
    assert "ck_topics_state" not in {c["name"] for c in inspect(engine).get_check_constraints("topics")}


def test_v2_constraints(at_0008):
    _populate_v1()
    command.upgrade(CFG, "0009")
    with get_engine().begin() as c:
        c.execute(text("INSERT INTO selections (account_id, edition_date, topic_id) VALUES (1, '2026-11-27', 1)"))
        c.execute(text("INSERT INTO editions (edition_date, participants) VALUES ('2026-11-27', 1)"))
        c.execute(text(
            "INSERT INTO edition_topics (edition_id, rank, topic_id, title, summary, sources, source_count, article_count, approvals, proportion)"
            " VALUES (1, 1, 1, 'T', '', '[]', 2, 3, 1, 1.0)"
        ))
    for bad in (
        "INSERT INTO selections (account_id, edition_date, topic_id) VALUES (1, '2026-11-27', 1)",
        "INSERT INTO editions (edition_date, participants) VALUES ('2026-11-27', 0)",
        "INSERT INTO edition_topics (edition_id, rank, title, summary, sources, source_count, article_count, approvals, proportion)"
        " VALUES (1, 1, 'dup rank', '', '[]', 0, 0, 0, 0)",
        "INSERT INTO edition_topics (edition_id, rank, title, summary, sources, source_count, article_count, approvals, proportion)"
        " VALUES (1, 11, 'rank 11', '', '[]', 0, 0, 0, 0)",
    ):
        with pytest.raises(Exception), get_engine().begin() as c:
            c.execute(text(bad))
    with get_engine().begin() as c:  # deleting the topic keeps the frozen edition copy, drops the selection
        c.execute(text("DELETE FROM topics WHERE id = 1"))
        assert c.scalar(text("SELECT topic_id FROM edition_topics")) is None
        assert c.scalar(text("SELECT count(*) FROM edition_topics")) == 1
        assert c.scalar(text("SELECT count(*) FROM selections")) == 0
        c.execute(text("DELETE FROM editions"))
        assert c.scalar(text("SELECT count(*) FROM edition_topics")) == 0


def test_downgrade_recreates_empty_v1_structures(at_0008):
    _populate_v1()
    command.upgrade(CFG, "0009")
    command.downgrade(CFG, "0008")
    engine = get_engine()
    tables = set(inspect(engine).get_table_names())
    assert "votes" in tables and not V2_TABLES & tables
    assert "draft" not in _columns("login_tokens")
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM votes")) == 0  # the data is gone for good
        assert c.scalar(text("SELECT count(*) FROM topics")) == 2
        assert [tuple(r) for r in c.execute(text("SELECT state, wave, votes_at_eval, state_changed_at FROM topics"))] == [("new", 0, 0, None)] * 2
    with pytest.raises(Exception), engine.begin() as c:
        c.execute(text("UPDATE topics SET state = 'bogus'"))

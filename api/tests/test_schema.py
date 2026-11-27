from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Account, Edition, EditionTopic, LoginToken, Selection, Topic

DAY = date(2026, 11, 27)


def _account_and_topic(session):
    account = Account(email="a@example.org")
    topic = Topic(title="Sujet")
    session.add_all([account, topic])
    session.commit()
    return account, topic


def test_one_selection_per_account_day_and_topic(session):
    account, topic = _account_and_topic(session)
    session.add(Selection(account_id=account.id, edition_date=DAY, topic_id=topic.id))
    session.commit()
    session.add(Selection(account_id=account.id, edition_date=DAY, topic_id=topic.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_same_topic_can_be_selected_on_another_day_and_by_another_account(session):
    account, topic = _account_and_topic(session)
    other = Account(email="b@example.org")
    session.add(other)
    session.commit()
    session.add_all([
        Selection(account_id=account.id, edition_date=DAY, topic_id=topic.id),
        Selection(account_id=account.id, edition_date=date(2026, 11, 28), topic_id=topic.id),
        Selection(account_id=other.id, edition_date=DAY, topic_id=topic.id),
    ])
    session.commit()


def test_deleting_account_or_topic_removes_its_selections(session):
    account, topic = _account_and_topic(session)
    session.add(Selection(account_id=account.id, edition_date=DAY, topic_id=topic.id))
    session.commit()
    session.delete(topic)
    session.commit()
    assert session.query(Selection).count() == 0


def test_edition_date_is_unique(session):
    session.add(Edition(edition_date=DAY, participants=0))
    session.commit()
    session.add(Edition(edition_date=DAY, participants=3))
    with pytest.raises(IntegrityError):
        session.commit()


def _edition_topic(edition_id, rank, topic_id=None):
    return EditionTopic(
        edition_id=edition_id, rank=rank, topic_id=topic_id, title="T", summary="", sources=[],
        source_count=0, article_count=0, approvals=1, proportion=0.5,
    )


def test_edition_topic_rank_is_unique_and_bounded(session):
    edition = Edition(edition_date=DAY, participants=2)
    session.add(edition)
    session.commit()
    session.add(_edition_topic(edition.id, 1))
    session.commit()
    session.add(_edition_topic(edition.id, 1))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(_edition_topic(edition.id, 11))
    with pytest.raises(IntegrityError):
        session.commit()


def test_edition_topic_survives_its_topic_and_keeps_its_sources(session):
    _, topic = _account_and_topic(session)
    edition = Edition(edition_date=DAY, participants=1)
    session.add(edition)
    session.commit()
    row = _edition_topic(edition.id, 1, topic.id)
    row.sources = [{"name": "A", "url": "https://a.example/1", "title": "t", "published_at": None}]
    session.add(row)
    session.commit()
    session.delete(topic)
    session.commit()
    session.refresh(row)
    assert row.topic_id is None and row.sources[0]["name"] == "A"


def test_login_token_draft_is_optional_json(session):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    session.add_all([
        LoginToken(email="a@example.org", token_hash="1", expires_at=now),
        LoginToken(email="a@example.org", token_hash="2", expires_at=now, draft={"topic_ids": [1, 2]}),
    ])
    session.commit()
    drafts = {t.token_hash: t.draft for t in session.query(LoginToken)}
    assert drafts == {"1": None, "2": {"topic_ids": [1, 2]}}


def test_topic_has_no_halving_columns(session):
    topic = Topic(title="x")
    session.add(topic)
    session.commit()
    session.refresh(topic)
    assert not {"state", "wave", "evaluated_at", "votes_at_eval"} & set(Topic.__table__.columns.keys())
    assert topic.updated_at is not None

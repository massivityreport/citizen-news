import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Account, Topic, Vote


def _account_and_topic(session):
    account = Account(email="a@example.org")
    topic = Topic(title="Sujet")
    session.add_all([account, topic])
    session.commit()
    return account, topic


def test_one_vote_per_account_and_topic(session):
    account, topic = _account_and_topic(session)
    session.add(Vote(account_id=account.id, topic_id=topic.id, choice="more"))
    session.commit()
    session.add(Vote(account_id=account.id, topic_id=topic.id, choice="unknown"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_same_account_can_vote_on_different_topics(session):
    account, topic = _account_and_topic(session)
    other = Topic(title="Autre sujet")
    session.add(other)
    session.commit()
    session.add_all([
        Vote(account_id=account.id, topic_id=topic.id, choice="more"),
        Vote(account_id=account.id, topic_id=other.id, choice="not_priority"),
    ])
    session.commit()


def test_invalid_vote_choice_rejected(session):
    account, topic = _account_and_topic(session)
    session.add(Vote(account_id=account.id, topic_id=topic.id, choice="love"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_invalid_topic_state_rejected(session):
    session.add(Topic(title="x", state="bogus"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_topic_defaults(session):
    topic = Topic(title="x")
    session.add(topic)
    session.commit()
    session.refresh(topic)
    assert (topic.state, topic.wave) == ("new", 0)

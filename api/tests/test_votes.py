import pytest
from sqlalchemy import func, select

from app.models import Vote


def vote(client, topic_id, choice="more"):
    return client.post("/api/votes", json={"topic_id": topic_id, "choice": choice})


def test_vote_creates_and_returns_only_the_vote(logged, topics, session):
    r = vote(logged, topics[0], "more")
    assert r.status_code == 200
    # results stay hidden: nothing but the vote itself
    assert r.json() == {"topic_id": topics[0], "choice": "more"}
    assert logged.get("/api/votes/mine").json() == {"votes": [{"topic_id": topics[0], "choice": "more"}]}


def test_vote_replaces_and_keeps_a_single_row(logged, topics, session):
    vote(logged, topics[0], "more")
    row = session.scalar(select(Vote))
    first_update = row.updated_at
    assert vote(logged, topics[0], "not_priority").json()["choice"] == "not_priority"
    assert vote(logged, topics[0], "unknown").json()["choice"] == "unknown"
    session.expire_all()
    rows = session.scalars(select(Vote)).all()
    assert len(rows) == 1 and rows[0].choice == "unknown"
    assert rows[0].updated_at > first_update and rows[0].created_at == row.created_at


def test_one_vote_per_topic_for_each_account(logged, topics, session):
    vote(logged, topics[0])
    vote(logged, topics[1])
    vote(logged, topics[1], "unknown")
    assert session.scalar(select(func.count()).select_from(Vote)) == 2


def test_vote_requires_session(client, topics, session):
    r = vote(client, topics[0])
    assert r.status_code == 401 and r.json() == {"detail": "Authentification requise"}
    assert session.scalar(select(func.count()).select_from(Vote)) == 0


def test_vote_unknown_topic(logged, topics):
    r = vote(logged, 99999)
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)


@pytest.mark.parametrize(
    "payload",
    [{"topic_id": 1, "choice": "love"}, {"topic_id": 1}, {"choice": "more"}, {"topic_id": "x", "choice": "more"}],
)
def test_vote_rejects_invalid_payload(logged, topics, payload):
    r = logged.post("/api/votes", json=payload)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


def test_vote_rate_limit(logged, topics, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_VOTE_PER_ACCOUNT", "3")
    get_settings.cache_clear()
    try:
        codes = [vote(logged, topics[i % 3]).status_code for i in range(4)]
        assert codes == [200, 200, 200, 429]
        limited = vote(logged, topics[0])
        assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_vote_rate_limit_is_per_account(logged, topics, session, monkeypatch):
    from app.deps import SESSION_COOKIE
    from app.models import Account
    from app.services import auth
    from config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_VOTE_PER_ACCOUNT", "1")
    get_settings.cache_clear()
    try:
        assert vote(logged, topics[0]).status_code == 200
        assert vote(logged, topics[0]).status_code == 429
        other = Account(email="b@example.org")
        session.add(other)
        session.commit()
        token, _ = auth.create_session(session, other)
        logged.cookies.set(SESSION_COOKIE, token)
        assert vote(logged, topics[0]).status_code == 200
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

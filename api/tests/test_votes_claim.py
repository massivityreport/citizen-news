import pytest
from sqlalchemy import select

from app.models import Account, Topic, Vote
from app.services import auth
from app.deps import SESSION_COOKIE


@pytest.fixture
def topics(session):
    ts = [Topic(title=f"Sujet {i}") for i in range(3)]
    session.add_all(ts)
    session.commit()
    return [t.id for t in ts]


@pytest.fixture
def logged(client, session):
    account = Account(email="a@example.org")
    session.add(account)
    session.commit()
    token, _ = auth.create_session(session, account)
    client.cookies.set(SESSION_COOKIE, token)
    client.account_id = account.id
    return client


def claim(client, votes):
    return client.post("/api/votes/claim", json={"votes": votes})


def test_claim_creates_votes_and_mine_lists_them(logged, topics):
    r = claim(logged, [{"topic_id": topics[1], "choice": "more"}, {"topic_id": topics[0], "choice": "not_priority"}])
    assert (r.status_code, r.json()) == (200, {"claimed": 2})
    assert logged.get("/api/votes/mine").json() == {
        "votes": [{"topic_id": topics[0], "choice": "not_priority"}, {"topic_id": topics[1], "choice": "more"}]
    }


def test_claim_does_not_overwrite_existing_vote(logged, topics, session):
    session.add(Vote(account_id=logged.account_id, topic_id=topics[0], choice="more"))
    session.commit()
    r = claim(logged, [{"topic_id": topics[0], "choice": "not_priority"}, {"topic_id": topics[1], "choice": "unknown"}])
    assert r.json() == {"claimed": 1}
    choices = dict(session.execute(select(Vote.topic_id, Vote.choice)).all())
    assert choices == {topics[0]: "more", topics[1]: "unknown"}


def test_claim_is_idempotent(logged, topics):
    votes = [{"topic_id": topics[0], "choice": "more"}]
    assert claim(logged, votes).json() == {"claimed": 1}
    assert claim(logged, votes).json() == {"claimed": 0}


def test_claim_ignores_unknown_topics(logged, topics):
    r = claim(logged, [{"topic_id": 99999, "choice": "more"}, {"topic_id": topics[0], "choice": "more"}])
    assert r.json() == {"claimed": 1}


def test_claim_duplicate_topic_in_batch_counts_once_first_wins(logged, topics):
    r = claim(logged, [{"topic_id": topics[0], "choice": "more"}, {"topic_id": topics[0], "choice": "unknown"}])
    assert r.json() == {"claimed": 1}
    assert logged.get("/api/votes/mine").json()["votes"] == [{"topic_id": topics[0], "choice": "more"}]


def test_claim_empty_batch(logged):
    assert claim(logged, []).json() == {"claimed": 0}


def test_claim_batch_cap(logged, topics, session):
    ok = [{"topic_id": topics[0], "choice": "more"}] * 200
    assert claim(logged, ok).status_code == 200
    r = claim(logged, ok + [{"topic_id": topics[1], "choice": "more"}])
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert session.scalar(select(Vote.id).where(Vote.topic_id == topics[1])) is None


@pytest.mark.parametrize("payload", [{"votes": [{"topic_id": 1, "choice": "love"}]}, {"votes": [{"choice": "more"}]}, {}])
def test_claim_rejects_malformed_payload(logged, payload):
    assert logged.post("/api/votes/claim", json=payload).status_code == 422


def test_claim_and_mine_require_session(client, topics):
    assert claim(client, [{"topic_id": topics[0], "choice": "more"}]).status_code == 401
    assert client.get("/api/votes/mine").status_code == 401


def test_votes_are_per_account(logged, topics, session):
    other = Account(email="b@example.org")
    session.add(other)
    session.commit()
    session.add(Vote(account_id=other.id, topic_id=topics[0], choice="more"))
    session.commit()
    assert logged.get("/api/votes/mine").json() == {"votes": []}
    assert claim(logged, [{"topic_id": topics[0], "choice": "unknown"}]).json() == {"claimed": 1}


def test_claim_rate_limit(logged, topics, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_CLAIM_PER_ACCOUNT", "2")
    get_settings.cache_clear()
    try:
        codes = [claim(logged, []).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert "retry-after" in claim(logged, []).headers
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_no_direct_vote_endpoint_yet(logged, topics):
    assert logged.post("/api/votes", json={"topic_id": topics[0], "choice": "more"}).status_code in (404, 405)


def test_claim_payload_hard_bound_at_parsing(logged, topics):
    r = claim(logged, [{"topic_id": topics[0], "choice": "more"}] * 1001)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)

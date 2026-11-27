"""The citizen's une: /api/me/une*."""

import threading
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.deps import clock
from app.models.entities import Account, Edition, Selection
from app.services import une
from tests.helpers import make_sources, make_topic

NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)  # 11:00 Paris: open, closes 16:00 UTC
DAY = date(2026, 11, 27)
CLOSED = datetime(2026, 11, 27, 16, 0, tzinfo=UTC)
UNE = "/api/me/une"


@pytest.fixture(autouse=True)
def now(client):
    client.app.dependency_overrides[clock] = lambda: NOW


@pytest.fixture
def media(session):
    return make_sources(session, "A", "B")


@pytest.fixture
def pool_ids(session, media):
    """12 topics of the pool (ids ascending)."""
    ids = [make_topic(session, f"T{i}", media, hours_ago=1 + i / 10, now=NOW).id for i in range(12)]
    session.commit()
    return ids


def put(c, topic_id):
    return c.put(f"{UNE}/topics/{topic_id}")


def ids_of(c):
    return c.get(UNE).json()["topic_ids"]


# --- session ---

@pytest.mark.parametrize("method, path, body", [
    ("get", UNE, None), ("put", UNE, {"topic_ids": []}), ("put", f"{UNE}/topics/1", None),
    ("delete", f"{UNE}/topics/1", None), ("post", f"{UNE}/merge", {"topic_ids": []}),
])
def test_session_required(client, method, path, body):
    r = getattr(client, method)(path, **({"json": body} if body is not None else {}))
    assert r.status_code == 401 and "detail" in r.json()


# --- read / add / remove ---

def test_empty_une_has_the_edition_envelope(logged):
    r = logged.get(UNE)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"edition_date": "2026-11-27", "closes_at": "2026-11-27T16:00:00Z", "open": True, "topic_ids": []}


def test_add_keeps_order_of_addition_and_is_idempotent(logged, pool_ids):
    a, b, c = pool_ids[5], pool_ids[2], pool_ids[9]
    for t in (a, b, c, b):
        r = put(logged, t)
        assert r.status_code == 200
    assert r.json()["topic_ids"] == [a, b, c]
    assert ids_of(logged) == [a, b, c]


def test_unknown_topic_is_404(logged, pool_ids):
    assert put(logged, 99999).status_code == 404


def test_topic_out_of_the_pool_is_refused_422(logged, session, media, pool_ids):
    old = make_topic(session, "vieux", media, hours_ago=30, now=NOW)
    mono = make_topic(session, "mono", media[:1], hours_ago=1, now=NOW)
    session.commit()
    for t in (old.id, mono.id):
        r = put(logged, t)
        assert r.status_code == 422 and r.json() == {"detail": "Ce sujet n'est plus au bassin du jour"}
    assert ids_of(logged) == []


def test_ten_places_max_then_409_but_known_topic_stays_idempotent(logged, pool_ids):
    for t in pool_ids[:10]:
        assert put(logged, t).status_code == 200
    r = put(logged, pool_ids[10])
    assert r.status_code == 409 and r.json() == {"detail": "Votre une est complète"}
    assert put(logged, pool_ids[0]).status_code == 200  # already in: no-op
    assert ids_of(logged) == pool_ids[:10]
    assert logged.delete(f"{UNE}/topics/{pool_ids[0]}").status_code == 200
    assert put(logged, pool_ids[10]).status_code == 200  # a place is free again


def test_delete_is_idempotent_and_ignores_unknown_topics(logged, pool_ids):
    put(logged, pool_ids[0])
    put(logged, pool_ids[1])
    r = logged.delete(f"{UNE}/topics/{pool_ids[0]}")
    assert r.json()["topic_ids"] == [pool_ids[1]]
    assert logged.delete(f"{UNE}/topics/{pool_ids[0]}").json()["topic_ids"] == [pool_ids[1]]
    assert logged.delete(f"{UNE}/topics/99999").status_code == 200


def test_une_is_per_account(logged, session, pool_ids):
    put(logged, pool_ids[0])
    other = Account(email="b@example.org")
    session.add(other)
    session.commit()
    from app.deps import SESSION_COOKIE
    from app.services import auth
    token, _ = auth.create_session(session, other)
    logged.cookies.set(SESSION_COOKIE, token)
    assert ids_of(logged) == []


def test_database_refuses_a_duplicate_row(logged, session, pool_ids):
    session.add(Selection(account_id=logged.account_id, edition_date=DAY, topic_id=pool_ids[0]))
    session.commit()
    session.add(Selection(account_id=logged.account_id, edition_date=DAY, topic_id=pool_ids[0]))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# --- replace ---

def test_replace_dedupes_keeps_places_and_orders_new_ones(logged, pool_ids):
    put(logged, pool_ids[3])
    put(logged, pool_ids[1])
    r = logged.put(UNE, json={"topic_ids": [pool_ids[7], pool_ids[1], pool_ids[7], pool_ids[0]]})
    assert r.status_code == 200
    assert r.json()["topic_ids"] == [pool_ids[1], pool_ids[7], pool_ids[0]]
    assert ids_of(logged) == r.json()["topic_ids"]


def test_replace_with_empty_list_clears_the_une(logged, pool_ids):
    put(logged, pool_ids[0])
    assert logged.put(UNE, json={"topic_ids": []}).json()["topic_ids"] == []


def test_replace_accepts_exactly_ten_and_refuses_more_than_ten(logged, pool_ids):
    assert logged.put(UNE, json={"topic_ids": pool_ids[:10]}).status_code == 200
    put_before = ids_of(logged)
    r = logged.put(UNE, json={"topic_ids": pool_ids[:11]})
    assert r.status_code == 422 and "detail" in r.json()
    assert ids_of(logged) == put_before  # nothing written
    # 11 entries but 10 distinct: deduplicated first, accepted
    assert logged.put(UNE, json={"topic_ids": pool_ids[:10] + [pool_ids[0]]}).status_code == 200


def test_replace_with_an_unknown_topic_is_422_and_changes_nothing(logged, pool_ids):
    put(logged, pool_ids[0])
    r = logged.put(UNE, json={"topic_ids": [pool_ids[1], 99999]})
    assert r.status_code == 422
    assert ids_of(logged) == [pool_ids[0]]


@pytest.mark.parametrize("body", [
    {}, {"topic_ids": "1"}, {"topic_ids": [0]}, {"topic_ids": [-1]}, {"topic_ids": ["a"]}, {"topic_ids": [1.5]},
    {"topic_ids": [2**40]}, {"topic_ids": [None]}, {"topic_ids": list(range(1, 200))},
])
def test_invalid_bodies_are_422(logged, body):
    for r in (logged.put(UNE, json=body), logged.post(f"{UNE}/merge", json=body)):
        assert r.status_code == 422 and "detail" in r.json()


# --- merge ---

def test_merge_adds_without_overwriting(logged, pool_ids):
    put(logged, pool_ids[0])
    put(logged, pool_ids[1])
    r = logged.post(f"{UNE}/merge", json={"topic_ids": [pool_ids[1], pool_ids[2], pool_ids[3], pool_ids[2]]})
    assert r.status_code == 200
    body = r.json()
    assert (body["added"], body["ignored"]) == (2, 0)  # an existing topic is neither added nor ignored
    assert body["une"]["topic_ids"] == [pool_ids[0], pool_ids[1], pool_ids[2], pool_ids[3]]
    assert ids_of(logged) == body["une"]["topic_ids"]
    assert set(body["une"]) == {"edition_date", "closes_at", "open", "topic_ids"}


def test_merge_ignores_unknown_and_out_of_pool_topics(logged, session, media, pool_ids):
    old = make_topic(session, "vieux", media, hours_ago=30, now=NOW)
    session.commit()
    r = logged.post(f"{UNE}/merge", json={"topic_ids": [pool_ids[0], 99999, old.id]})
    assert r.status_code == 200
    assert (r.json()["added"], r.json()["ignored"]) == (1, 2)
    assert ids_of(logged) == [pool_ids[0]]


def test_merge_stops_at_ten_places(logged, pool_ids):
    for t in pool_ids[:8]:
        put(logged, t)
    r = logged.post(f"{UNE}/merge", json={"topic_ids": pool_ids[8:10] + pool_ids[10:12]})
    assert (r.json()["added"], r.json()["ignored"]) == (2, 2)
    assert ids_of(logged) == pool_ids[:10]


def test_merge_into_a_full_une_changes_nothing(logged, pool_ids):
    logged.put(UNE, json={"topic_ids": pool_ids[:10]})
    r = logged.post(f"{UNE}/merge", json={"topic_ids": pool_ids[10:]})
    assert (r.json()["added"], r.json()["ignored"]) == (0, 2)
    assert ids_of(logged) == pool_ids[:10]


# --- closing ---

def test_writes_are_refused_after_closing_but_reading_works(client, logged, pool_ids):
    put(logged, pool_ids[0])
    client.app.dependency_overrides[clock] = lambda: CLOSED
    refused = [
        put(logged, pool_ids[1]),
        logged.delete(f"{UNE}/topics/{pool_ids[0]}"),
        logged.put(UNE, json={"topic_ids": []}),
        logged.post(f"{UNE}/merge", json={"topic_ids": [pool_ids[2]]}),
    ]
    for r in refused:
        assert r.status_code == 409
        assert r.json() == {"detail": "La clôture est passée, la une du jour n'est plus modifiable"}
    r = logged.get(UNE)
    assert r.status_code == 200 and r.json()["open"] is False and r.json()["topic_ids"] == [pool_ids[0]]


def test_last_second_is_still_open(client, logged, pool_ids):
    client.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 27, 15, 59, 59, tzinfo=UTC)
    assert put(logged, pool_ids[0]).status_code == 200


def test_after_publication_the_une_restarts_empty_for_the_next_edition(client, logged, session, pool_ids):
    put(logged, pool_ids[0])
    client.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 27, 16, 30, tzinfo=UTC)
    assert put(logged, pool_ids[1]).status_code == 409  # publication period: late worker
    session.add(Edition(edition_date=DAY, participants=1))  # the worker publishes
    session.commit()
    body = logged.get(UNE).json()
    assert body == {"edition_date": "2026-11-28", "closes_at": "2026-11-28T16:00:00Z", "open": True, "topic_ids": []}
    assert put(logged, pool_ids[1]).json()["topic_ids"] == [pool_ids[1]]
    # yesterday's une is untouched
    assert session.scalars(select(Selection.topic_id).where(Selection.edition_date == DAY)).all() == [pool_ids[0]]


# --- no counters ---

def test_no_approval_counter_in_any_response_or_error(client, logged, pool_ids):
    texts = [
        logged.get(UNE).text, put(logged, pool_ids[0]).text, put(logged, 99999).text,
        logged.post(f"{UNE}/merge", json={"topic_ids": pool_ids[:3]}).text,
        logged.delete(f"{UNE}/topics/{pool_ids[0]}").text, logged.put(UNE, json={"topic_ids": [0]}).text,
    ]
    client.app.dependency_overrides[clock] = lambda: CLOSED
    texts.append(put(logged, pool_ids[5]).text)
    for text in texts:
        assert not any(w in text.lower() for w in ("approval", "approbation", "score", "proportion", "participants"))


# --- rate limit ---

def test_writes_are_rate_limited_per_account(monkeypatch, client, logged, session, pool_ids):
    from app.deps import SESSION_COOKIE
    from app.services import auth
    from config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_UNE_WRITES_PER_ACCOUNT", "3")
    get_settings.cache_clear()
    try:
        for _ in range(3):
            assert put(logged, pool_ids[0]).status_code == 200
        r = put(logged, pool_ids[0])
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1 and "detail" in r.json()
        assert logged.delete(f"{UNE}/topics/{pool_ids[0]}").status_code == 429
        assert logged.get(UNE).status_code == 200  # reads are not limited
        other = Account(email="b@example.org")
        session.add(other)
        session.commit()
        token, _ = auth.create_session(session, other)
        logged.cookies.set(SESSION_COOKIE, token)
        assert put(logged, pool_ids[0]).status_code == 200  # another account has its own budget
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# --- concurrency ---

def _in_threads(jobs):
    barrier = threading.Barrier(len(jobs))
    results, errors = [], []

    def run(job):
        try:
            with Session(get_engine()) as s:
                barrier.wait(timeout=10)
                results.append(job(s))
        except Exception as e:  # collected, asserted by the caller
            errors.append(e)

    threads = [threading.Thread(target=run, args=(j,)) for j in jobs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def count(session, account_id):
    return session.scalar(select(func.count()).select_from(Selection).where(Selection.account_id == account_id))


def test_simultaneous_adds_never_exceed_ten(logged, session, pool_ids):
    for t in pool_ids[:8]:
        put(logged, t)
    jobs = [lambda s, t=t: une.add_topic(s, logged.account_id, t, NOW) for t in pool_ids[8:] * 3]  # 4 ids x 3 = 12 racers
    results, errors = _in_threads(jobs)
    assert all(isinstance(e, une.UneFull) for e in errors)
    assert len(results) == 6 and len(errors) == 6  # 2 free places: 2 topics x 3 idempotent calls succeed
    assert count(session, logged.account_id) == 10


def test_simultaneous_merges_never_exceed_ten(logged, session, pool_ids):
    jobs = [lambda s, i=i: une.merge(s, logged.account_id, pool_ids[i::3], NOW) for i in range(3)] * 4
    results, errors = _in_threads(jobs)
    assert not errors
    assert sum(r.added for r in results) == 10
    assert count(session, logged.account_id) == 10


def test_simultaneous_identical_adds_insert_one_row(logged, session, pool_ids):
    jobs = [lambda s: une.add_topic(s, logged.account_id, pool_ids[0], NOW)] * 8
    results, errors = _in_threads(jobs)
    assert not errors and len(results) == 8
    assert count(session, logged.account_id) == 1


# --- CORS ---

def test_cors_preflight_allows_put(monkeypatch, database_url):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from config.settings import get_settings

    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    get_settings.cache_clear()
    try:
        client = TestClient(create_app())
    finally:
        get_settings.cache_clear()
    r = client.options(UNE + "/topics/1", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT"})
    assert r.status_code == 200 and "PUT" in r.headers["access-control-allow-methods"]

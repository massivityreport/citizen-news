"""GET /api/topics/pool: eligibility, tabs, seed, cap, constant query count, no approval counters."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.db import get_engine
from app.deps import clock
from app.models.entities import Article, Edition, Selection, Topic
from app.services.pool import eligible_pool, random_key
from tests.helpers import make_article, make_sources, make_topic

NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)  # 11:00 Paris, winter: closes 16:00 UTC
SEED = "graine-0001"


@pytest.fixture
def pooled(client):
    client.app.dependency_overrides[clock] = lambda: NOW
    return client


@pytest.fixture
def media(session):
    return make_sources(session, "A", "B", "C", "D", "E")


def pool(client, **params):
    params.setdefault("seed", SEED)
    return client.get("/api/topics/pool", params=params)


def ids(response):
    return [i["id"] for i in response.json()["items"]]


def test_envelope_and_headers(pooled, session, media):
    make_topic(session, "T", media[:2], hours_ago=2, now=NOW)
    session.commit()
    r = pool(pooled)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert (body["edition_date"], body["closes_at"], body["open"], body["total"]) == ("2026-11-27", "2026-11-27T16:00:00Z", True, 1)
    assert set(body["items"][0]) == {"id", "title", "summary", "sources", "article_count", "source_count", "first_seen_at", "updated_at", "image_url"}


def test_pool_is_public_and_empty_pool_is_fine(pooled):
    r = pool(pooled)
    assert r.status_code == 200 and r.json()["items"] == [] and r.json()["total"] == 0


def test_eligibility_window_24h_and_two_distinct_media(pooled, session, media):
    a, b, c, *_ = media
    fresh = make_topic(session, "frais", [a, b], hours_ago=23, now=NOW)
    old = make_topic(session, "vieux", [a, b], hours_ago=25, now=NOW)  # inside the 48 h clustering window, outside the pool
    mono = make_topic(session, "un seul média", [a], hours_ago=1, now=NOW)
    make_article(session, a, "bis", "Encore un", hours_ago=2, now=NOW, topic_id=mono.id)  # 2 articles, 1 medium
    # one fresh article is enough even if the other media's articles are older
    mixed = make_topic(session, "mixte", [a, b], hours_ago=30, now=NOW)
    make_article(session, c, "frais", "Récent", hours_ago=1, now=NOW, topic_id=mixed.id)
    session.commit()
    assert set(ids(pool(pooled))) == {fresh.id, mixed.id}
    assert old.id not in ids(pool(pooled))


def test_article_without_published_at_uses_fetched_at(pooled, session, media):
    t = Topic(title="sans date")
    session.add(t)
    session.flush()
    for s in media[:2]:
        session.add(Article(source_id=s.id, url=f"https://x/{s.id}", title="x", published_at=None, fetched_at=NOW - timedelta(hours=2), topic_id=t.id))
    session.commit()
    assert ids(pool(pooled)) == [t.id]


def test_recent_tab_orders_by_updated_at_then_id_desc(pooled, session, media):
    old = make_topic(session, "old", media[:2], hours_ago=10, now=NOW)
    t1 = make_topic(session, "t1", media[:2], hours_ago=3, now=NOW)
    t2 = make_topic(session, "t2", media[:2], hours_ago=3, now=NOW)
    new = make_topic(session, "new", media[:2], hours_ago=1, now=NOW)
    t1.updated_at = t2.updated_at = NOW - timedelta(hours=3)
    session.commit()
    assert ids(pool(pooled, tab="recent")) == [new.id, t2.id, t1.id, old.id]


def test_radar_tab_keeps_low_coverage_only_in_recent_order(pooled, session, media):
    small = make_topic(session, "petit", media[:2], hours_ago=5, now=NOW)
    edge = make_topic(session, "limite", media[:3], hours_ago=2, now=NOW)
    big = make_topic(session, "gros", media[:4], hours_ago=1, now=NOW)
    session.commit()
    r = pool(pooled, tab="radar")
    assert ids(r) == [edge.id, small.id] and big.id not in ids(r)
    assert r.json()["total"] == 2


def test_random_tab_is_stable_per_seed_and_differs_between_seeds(pooled, session, media):
    topics = [make_topic(session, f"t{i}", media[:2], hours_ago=1 + i / 10, now=NOW) for i in range(12)]
    session.commit()
    first = ids(pool(pooled, seed="graine-AAAA"))
    assert first == ids(pool(pooled, seed="graine-AAAA"))
    assert first == sorted((t.id for t in topics), key=lambda i: random_key("graine-AAAA", i))
    assert first != ids(pool(pooled, seed="graine-BBBB"))
    assert sorted(first) == sorted(t.id for t in topics)
    # random is the default tab
    assert ids(pooled.get("/api/topics/pool", params={"seed": "graine-AAAA"})) == first


def test_random_order_ignores_freshness_and_coverage(pooled, session, media):
    # No weighting: the order only depends on seed and id, whatever the topic looks like.
    a = make_topic(session, "a", media[:2], hours_ago=20, now=NOW)
    b = make_topic(session, "b", media, hours_ago=1, now=NOW)
    session.commit()
    expected = sorted([a.id, b.id], key=lambda i: random_key(SEED, i))
    assert ids(pool(pooled)) == expected


@pytest.mark.parametrize("params", [
    {"tab": "random"},  # seed missing
    {"tab": "random", "seed": "court"},
    {"tab": "random", "seed": "x" * 65},
    {"tab": "random", "seed": "avec espace!"},
    {"tab": "recent", "seed": "bad seed!!"},
    {"tab": "inconnu", "seed": SEED},
])
def test_invalid_parameters_are_422(pooled, params):
    r = pooled.get("/api/topics/pool", params=params)
    assert r.status_code == 422 and "detail" in r.json()


def test_seed_is_optional_for_recent_and_radar(pooled):
    assert pooled.get("/api/topics/pool", params={"tab": "recent"}).status_code == 200
    assert pooled.get("/api/topics/pool", params={"tab": "radar"}).status_code == 200


def test_cap_300_but_total_counts_everything(pooled, session, media):
    for i in range(305):
        t = Topic(title=f"t{i}", summary="", first_seen_at=NOW, updated_at=NOW - timedelta(hours=2))
        session.add(t)
        session.flush()
        session.add_all([Article(source_id=s.id, url=f"https://x/{i}/{s.id}", title="x", published_at=NOW - timedelta(hours=2), topic_id=t.id) for s in media[:2]])
    session.commit()
    body = pool(pooled).json()
    assert body["total"] == 305 and len(body["items"]) == 300


def test_closed_pool_still_served_with_open_false(client, session, media):
    client.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 27, 16, 5, tzinfo=UTC)
    make_topic(session, "T", media[:2], hours_ago=1, now=NOW)
    session.commit()
    body = pool(client).json()
    assert (body["edition_date"], body["open"], len(body["items"])) == ("2026-11-27", False, 1)
    session.add(Edition(edition_date=datetime(2026, 11, 27).date(), participants=0))
    session.commit()
    body = pool(client).json()
    assert (body["edition_date"], body["closes_at"], body["open"]) == ("2026-11-28", "2026-11-28T16:00:00Z", True)


def test_no_approval_or_score_anywhere_in_the_response(pooled, session, media, logged):
    # Even with accounts having these topics in their une, nothing about it leaks.
    t = make_topic(session, "T", media[:2], hours_ago=1, now=NOW)
    session.commit()
    session.add(Selection(account_id=logged.account_id, edition_date=datetime(2026, 11, 27).date(), topic_id=t.id))
    session.commit()
    top = {"edition_date", "closes_at", "open", "total", "items"}
    card = {"id", "title", "summary", "sources", "article_count", "source_count", "first_seen_at", "updated_at", "image_url"}
    source = {"name", "url", "title", "published_at"}
    for tab in ("random", "recent", "radar"):
        body = pool(pooled, tab=tab).json()
        assert set(body) == top and body["items"]
        for item in body["items"]:
            assert set(item) == card
            assert all(set(src) == source for src in item["sources"])
        text = pool(pooled, tab=tab).text.lower()
        assert not any(word in text for word in ("approval", "approbation", "score", "proportion"))


def query_count(client, **params):
    n = []
    engine = get_engine()
    listener = lambda *a, **k: n.append(1)
    event.listen(engine, "before_cursor_execute", listener)
    try:
        assert pool(client, **params).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(n)


def test_query_count_is_constant_whatever_the_number_of_topics(pooled, session, media):
    make_topic(session, "T0", media[:2], hours_ago=1, now=NOW)
    session.commit()
    few = {tab: query_count(pooled, tab=tab) for tab in ("random", "recent", "radar")}
    for i in range(1, 40):
        make_topic(session, f"T{i}", media[: 2 + i % 3], hours_ago=1 + i / 10, now=NOW)
    session.commit()
    many = {tab: query_count(pooled, tab=tab) for tab in ("random", "recent", "radar")}
    assert few == many
    assert max(many.values()) <= 6


def test_eligible_pool_single_aggregated_query_and_topic_filter(session, media):
    a = make_topic(session, "a", media[:2], hours_ago=1, now=NOW)
    b = make_topic(session, "b", media[:2], hours_ago=1, now=NOW)
    session.commit()
    a_id, b_id = a.id, b.id
    n = []
    listener = lambda *args, **kw: n.append(1)
    event.listen(get_engine(), "before_cursor_execute", listener)
    try:
        assert {e.topic_id for e in eligible_pool(session, NOW)} == {a_id, b_id}
        assert {e.topic_id for e in eligible_pool(session, NOW, topic_ids=[b_id, 999])} == {b_id}
    finally:
        event.remove(get_engine(), "before_cursor_execute", listener)
    assert len(n) == 2


def test_future_dated_articles_do_not_keep_a_topic_in_the_pool(pooled, session, media):
    stale = make_topic(session, "vieux", media[:2], hours_ago=30, now=NOW)
    make_article(session, media[2], "futur", "Date folle", hours_ago=-72, now=NOW, topic_id=stale.id)  # 3 days ahead
    ok = make_topic(session, "ok", media[:2], hours_ago=30, now=NOW)
    make_article(session, media[2], "bientot", "Horloge en avance", hours_ago=-0.5, now=NOW, topic_id=ok.id)  # within 1 h: kept
    session.commit()
    assert ids(pool(pooled)) == [ok.id]

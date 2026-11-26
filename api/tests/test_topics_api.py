from datetime import UTC, datetime

import pytest

from app.services.clustering import cluster
from config.clustering import ClusteringParams
from tests.helpers import FOOT, METEO, RETRAITES, make_article, make_sources

NOW = datetime.now(UTC)
CARD_KEYS = {"id", "title", "summary", "sources", "first_seen_at", "updated_at"}


@pytest.fixture
def world(session):
    """3 topics: retraites (3 media), foot (2 media), météo (1 medium, twice) + clustering done."""
    a, b, c = make_sources(session, "Média A", "Média B", "Média C")
    make_article(session, a, 1, *RETRAITES[0], hours_ago=6, now=NOW)
    make_article(session, b, 2, *RETRAITES[1], hours_ago=5, now=NOW)
    make_article(session, c, 3, *RETRAITES[2], hours_ago=4, now=NOW)
    make_article(session, a, 4, *FOOT, hours_ago=2, now=NOW)
    make_article(session, b, 5, "PSG - OM : Paris s'impose 2-0 dans le Classique", FOOT[1], hours_ago=1, now=NOW)
    make_article(session, a, 6, *METEO, hours_ago=3, now=NOW)
    make_article(session, a, 7, "Canicule : la vigilance orange touche douze départements du sud", METEO[1], hours_ago=3, now=NOW)
    session.commit()
    cluster(session, ClusteringParams(), now=NOW)


def test_front_contract_and_filtering(client, world):
    response = client.get("/api/topics/front")
    assert response.status_code == 200
    items = response.json()["items"]
    # météo has two articles but a single medium: not on the front page
    assert len(items) == 2
    for item in items:
        assert set(item) == CARD_KEYS | {"support", "reason"}
        assert item["support"] == {"level": "low", "votes_count": 0}
        assert item["reason"]["code"] == "emerging" and item["reason"]["label"]
        assert item["first_seen_at"].endswith("Z") and item["updated_at"].endswith("Z")
        assert set(item["sources"][0]) == {"name", "url", "title", "published_at"}
        assert len({s["name"] for s in item["sources"]}) == len(item["sources"])
    # freshest first (foot updated 1h ago, retraites 4h ago)
    assert [len(i["sources"]) for i in items] == [2, 3]
    assert items[0]["updated_at"] > items[1]["updated_at"]


def test_front_limit_and_validation(client, world):
    assert len(client.get("/api/topics/front?limit=1").json()["items"]) == 1
    for bad in ("0", "51", "abc"):
        assert client.get(f"/api/topics/front?limit={bad}").status_code == 422


def test_front_empty(client, session):
    assert client.get("/api/topics/front").json() == {"items": []}


def test_front_uses_a_constant_number_of_queries(client, world, session):
    from sqlalchemy import event

    from app.db import get_engine

    statements = []
    engine = get_engine()
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        client.get("/api/topics/front")
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(statements) <= 3


def test_vote_next_has_no_support_and_respects_count_and_seen(client, world):
    items = client.get("/api/vote/next?count=10").json()["items"]
    assert len(items) == 2
    assert all(set(i) == CARD_KEYS for i in items)
    first, second = (i["id"] for i in items)
    assert len(client.get("/api/vote/next?count=1").json()["items"]) == 1
    only = client.get(f"/api/vote/next?seen={first}").json()["items"]
    assert [i["id"] for i in only] == [second]
    assert client.get(f"/api/vote/next?seen={first},{second}").json() == {"items": []}
    assert client.get("/api/vote/next?seen=").status_code == 200


def test_vote_next_validation(client, world):
    for query in ("count=0", "count=21", "seen=1,x"):
        response = client.get(f"/api/vote/next?{query}")
        assert response.status_code == 422, query


def test_vote_next_rotates_randomly(client, world):
    firsts = {client.get("/api/vote/next?count=1").json()["items"][0]["id"] for _ in range(40)}
    assert len(firsts) == 2

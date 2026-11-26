from datetime import UTC, datetime

import pytest

from app.services.clustering import cluster
from config.clustering import ClusteringParams
from tests.helpers import FOOT, METEO, RETRAITES, make_article, make_sources, make_topic

NOW = datetime.now(UTC)
CARD_KEYS = {"id", "title", "summary", "sources", "first_seen_at", "updated_at", "image_url"}


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
    assert client.get("/api/topics/front").json() == {"items": [], "has_more": False}


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


# --- image_url: image of the topic's most recent article that has one ---


def _set_images(session, **by_number):
    from sqlalchemy import update

    from app.models.entities import Article

    for n, image in by_number.items():
        session.execute(update(Article).where(Article.url.like(f"%/a/{n[1:]}")).values(image_url=image))
    session.commit()


def _images_by_title(client, path):
    from app.routers.topics import clear_front_cache

    clear_front_cache()
    return {i["title"]: i["image_url"] for i in client.get(path).json()["items"]}


def test_card_image_is_null_when_no_article_has_one(client, world):
    for path in ("/api/topics/front", "/api/vote/next"):
        images = _images_by_title(client, path)
        assert len(images) == 2 and set(images.values()) == {None}


def test_card_image_comes_from_the_most_recent_article_with_one(client, session, world):
    # retraites: articles 1 (6h ago), 2 (5h ago), 3 (4h ago); foot: 4 (2h ago), 5 (1h ago)
    _set_images(session, a1="https://cdn.example/1.jpg", a2="https://cdn.example/2.jpg")  # 3 has none
    for path in ("/api/topics/front", "/api/vote/next"):
        images = _images_by_title(client, path)
        retraites = next(v for k, v in images.items() if "etraites" in k)
        assert retraites == "https://cdn.example/2.jpg"  # the newest article is bare: fall back to the next one
        assert [v for k, v in images.items() if "etraites" not in k] == [None]  # foot: no image
    _set_images(session, a3="https://cdn.example/3.jpg", a4="https://cdn.example/4.jpg")
    images = _images_by_title(client, "/api/topics/front")
    assert sorted(v for v in images.values()) == ["https://cdn.example/3.jpg", "https://cdn.example/4.jpg"]


def test_card_image_ties_on_published_at_go_to_the_highest_id(client, session, world):
    from sqlalchemy import update

    from app.models.entities import Article

    same = datetime.now(UTC)
    session.execute(update(Article).where(Article.url.like("%/a/1") | Article.url.like("%/a/2")).values(published_at=same))
    session.commit()
    _set_images(session, a1="https://cdn.example/1.jpg", a2="https://cdn.example/2.jpg")
    retraites = next(v for k, v in _images_by_title(client, "/api/vote/next").items() if "etraites" in k)
    assert retraites == "https://cdn.example/2.jpg"


def _count_statements(client, path):
    from sqlalchemy import event

    from app.db import get_engine
    from app.routers.topics import clear_front_cache

    clear_front_cache()
    statements = []
    engine = get_engine()
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        items = client.get(path).json()["items"]
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(statements), items


def test_number_of_queries_does_not_depend_on_topics_with_images(client, session):
    from sqlalchemy import update

    from app.models.entities import Article
    from tests.helpers import make_topic

    a, b = make_sources(session, "A", "B")

    def add_topics(names):
        for name in names:
            make_topic(session, name, [a, b], hours_ago=3)
        session.execute(update(Article).where(Article.image_url.is_(None)).values(image_url="https://cdn.example/i.jpg"))
        session.commit()

    add_topics(["Un", "Deux"])
    small = {p: _count_statements(client, p) for p in ("/api/topics/front?limit=50", "/api/vote/next?count=20")}
    add_topics(["Trois", "Quatre", "Cinq", "Six", "Sept"])
    for path, (n_small, items_small) in small.items():
        n_big, items_big = _count_statements(client, path)
        assert len(items_small) == 2 and len(items_big) == 7
        assert all(i["image_url"] == "https://cdn.example/i.jpg" for i in items_big)
        assert n_big == n_small, path

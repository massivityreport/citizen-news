"""TopicCard building (services/topics.py): the public routes using it come with the V2 pool task."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, update

from app.db import get_engine
from app.models.entities import Article, Topic
from app.services.clustering import cluster
from app.services.topics import build_cards, eligible_topics
from config.clustering import ClusteringParams
from tests.helpers import FOOT, METEO, RETRAITES, make_article, make_sources, make_topic

NOW = datetime.now(UTC)
CARD_KEYS = {
    "id", "title", "summary", "sources", "article_count", "source_count", "first_seen_at", "updated_at", "image_url",
}


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


def cards(session):
    topics = list(session.scalars(eligible_topics(ClusteringParams()).order_by(Topic.updated_at.desc(), Topic.id.desc())))
    return build_cards(session, topics)


def test_eligibility_needs_two_distinct_media(session, world):
    # météo has two articles but a single medium
    assert [len(c.sources) for c in cards(session)] == [2, 3]


def test_card_contract(session, world):
    items = cards(session)
    for item in items:
        dumped = item.model_dump(mode="json")
        assert set(dumped) == CARD_KEYS
        assert len({s["name"] for s in dumped["sources"]}) == len(dumped["sources"])
        assert set(dumped["sources"][0]) == {"name", "url", "title", "published_at"}
    assert [(c.article_count, c.source_count) for c in items] == [(2, 2), (3, 3)]
    assert items[0].updated_at > items[1].updated_at


def test_card_counts_distinct_media_not_articles(session):
    a, b = make_sources(session, "A", "B")
    topic = make_topic(session, "Sujet", [a, b], now=NOW)
    make_article(session, a, "bis", "Sujet encore", hours_ago=1, now=NOW, topic_id=topic.id)
    session.commit()
    (card,) = build_cards(session, [topic])
    assert (card.article_count, card.source_count) == (3, 2)
    assert len(card.sources) == 2


def test_cluster_bumps_topic_updated_at_when_it_attaches_a_new_article(session):
    a, b, c = make_sources(session, "A", "B", "C")
    make_article(session, a, 1, *RETRAITES[0], hours_ago=6, now=NOW)
    make_article(session, b, 2, *RETRAITES[1], hours_ago=5, now=NOW)
    session.commit()
    cluster(session, ClusteringParams(), now=NOW)
    topic = session.query(Topic).one()
    before = topic.updated_at
    make_article(session, c, 3, *RETRAITES[2], hours_ago=1, now=NOW)
    session.commit()
    cluster(session, ClusteringParams(), now=NOW)
    session.expire_all()
    topic = session.query(Topic).one()
    assert topic.updated_at > before
    assert abs((topic.updated_at - (NOW - timedelta(hours=1))).total_seconds()) < 1


def _set_images(session, **by_article):
    for key, url in by_article.items():
        n = key[1:]
        session.execute(update(Article).where(Article.url.like(f"%/a/{n}")).values(image_url=url))
    session.commit()


def _images(session):
    return {c.title: c.image_url for c in cards(session)}


def test_card_image_is_null_when_no_article_has_one(session, world):
    images = _images(session)
    assert len(images) == 2 and set(images.values()) == {None}


def test_card_image_comes_from_the_most_recent_article_with_one(session, world):
    # retraites: articles 1 (6h ago), 2 (5h ago), 3 (4h ago); foot: 4 (2h ago), 5 (1h ago)
    _set_images(session, a1="https://cdn.example/1.jpg", a2="https://cdn.example/2.jpg")  # 3 has none
    images = _images(session)
    retraites = next(v for k, v in images.items() if "etraites" in k)
    assert retraites == "https://cdn.example/2.jpg"  # the newest article is bare: fall back to the next one
    assert [v for k, v in images.items() if "etraites" not in k] == [None]  # foot: no image
    _set_images(session, a3="https://cdn.example/3.jpg", a4="https://cdn.example/4.jpg")
    assert sorted(_images(session).values()) == ["https://cdn.example/3.jpg", "https://cdn.example/4.jpg"]


def test_card_image_ties_on_published_at_go_to_the_highest_id(session, world):
    same = datetime.now(UTC)
    session.execute(update(Article).where(Article.url.like("%/a/1") | Article.url.like("%/a/2")).values(published_at=same))
    session.commit()
    _set_images(session, a1="https://cdn.example/1.jpg", a2="https://cdn.example/2.jpg")
    retraites = next(v for k, v in _images(session).items() if "etraites" in k)
    assert retraites == "https://cdn.example/2.jpg"


def _count_statements(session):
    statements = []
    engine = get_engine()
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        items = cards(session)
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    return len(statements), items


def test_number_of_queries_does_not_depend_on_the_number_of_topics(session):
    a, b = make_sources(session, "A", "B")

    def add_topics(names):
        for name in names:
            make_topic(session, name, [a, b], hours_ago=3)
        session.execute(update(Article).where(Article.image_url.is_(None)).values(image_url="https://cdn.example/i.jpg"))
        session.commit()

    add_topics(["Un", "Deux"])
    n_small, items_small = _count_statements(session)
    add_topics(["Trois", "Quatre", "Cinq", "Six", "Sept"])
    n_big, items_big = _count_statements(session)
    assert len(items_small) == 2 and len(items_big) == 7
    assert all(i.image_url == "https://cdn.example/i.jpg" for i in items_big)
    assert n_big == n_small

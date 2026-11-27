"""Back office: topics list and topic detail (V1 votes / halving states are gone)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Account, Topic
from tests.helpers import make_article, make_sources, make_topic
from tests.test_admin_articles import count_queries
from tests.test_admin_auth import PASSWORD

LIST = "/api/admin/topics"


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


# --- access ----------------------------------------------------------------

ROUTES = [LIST, f"{LIST}/1"]


@pytest.mark.parametrize("url", ROUTES)
def test_401_without_session(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", ROUTES)
def test_401_with_citizen_session(logged, url):
    assert logged.get(url).status_code == 401


def test_votes_route_is_gone(admin):
    assert admin.get(f"{LIST}/1/votes").status_code == 404


# --- list ------------------------------------------------------------------

@pytest.fixture
def listing(session):
    s1, s2, s3 = make_sources(session, "A", "B", "C")
    big = make_topic(session, "Beta", [s1, s2, s3], hours_ago=3)
    make_article(session, s1, "extra", "Deuxième article de A", hours_ago=0.5, topic_id=big.id, image_url="https://img.example/new.jpg")
    make_article(session, s2, "old", "Vieux", hours_ago=30, topic_id=big.id, image_url="https://img.example/old.jpg")
    small = make_topic(session, "alpha", [s1], hours_ago=1)
    bare = make_topic(session, "Gamma", [], hours_ago=5)
    session.commit()
    return big.id, small.id, bare.id


def test_aggregates_without_any_vote_or_state_field(admin, listing):
    big, small, bare = listing
    items = {i["id"]: i for i in admin.get(LIST).json()["items"]}
    assert set(items[big]) == {"id", "title", "updated_at", "article_count", "source_count", "approvals", "image_url"}
    assert items[big]["title"] == "Beta" and items[big]["updated_at"].endswith("Z")
    assert (items[big]["article_count"], items[big]["source_count"]) == (5, 3)
    assert items[big]["image_url"] == "https://img.example/new.jpg"
    assert (items[small]["article_count"], items[small]["source_count"], items[small]["image_url"]) == (1, 1, None)
    assert (items[bare]["article_count"], items[bare]["source_count"]) == (0, 0)


@pytest.mark.parametrize("sort, order, expected", [
    ("articles", "desc", ["Beta", "alpha", "Gamma"]),
    ("articles", "asc", ["Gamma", "alpha", "Beta"]),
    ("title", "asc", ["alpha", "Beta", "Gamma"]),  # case-insensitive
    ("title", "desc", ["Gamma", "Beta", "alpha"]),
    ("updated", "desc", ["alpha", "Beta", "Gamma"]),
    ("updated", "asc", ["Gamma", "Beta", "alpha"]),
])
def test_sorts(admin, listing, sort, order, expected):
    res = admin.get(LIST, params={"sort": sort, "order": order})
    assert [i["title"] for i in res.json()["items"]] == expected


def test_default_sort_is_approvals_then_id(admin, listing):
    # no approval anywhere: ties on approvals break on id, descending like the sort
    big, small, bare = listing
    assert [i["id"] for i in admin.get(LIST).json()["items"]] == [bare, small, big]


def test_ties_break_on_id(admin, session):
    for _ in "xyz":
        session.add(Topic(title="Même titre"))
    session.commit()
    asc = [i["id"] for i in admin.get(LIST, params={"sort": "title", "order": "asc"}).json()["items"]]
    desc = [i["id"] for i in admin.get(LIST, params={"sort": "title", "order": "desc"}).json()["items"]]
    assert asc == sorted(asc) and desc == sorted(desc, reverse=True)


def test_pagination(admin, listing):
    page = admin.get(LIST, params={"page": 2, "page_size": 2, "sort": "title", "order": "asc"}).json()
    assert [i["title"] for i in page["items"]] == ["Gamma"] and page["total"] == 3
    assert admin.get(LIST, params={"page": 5}).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"sort": "id"}, {"sort": "votes"}, {"sort": "state"}, {"sort": "title; DROP TABLE topics"}, {"order": "x"},
    {"page": 0}, {"page_size": 201}, {"page_size": 0},
])
def test_list_422(admin, listing, params):
    assert admin.get(LIST, params=params).status_code == 422


def test_state_filter_is_gone(admin, listing):
    """`state` is no longer a parameter: unknown query parameters are ignored, nothing is filtered."""
    assert admin.get(LIST, params={"state": "reserve"}).json()["total"] == 3


def test_list_is_two_queries_whatever_the_number_of_topics(admin, session):
    from app.db import get_engine

    sources = make_sources(session, "A", "B")
    for i in range(12):
        make_topic(session, f"T{i}", sources)
    session.commit()
    stmts = count_queries(get_engine(), lambda: admin.get(LIST, params={"page_size": 200}))
    ours = [s for s in stmts if "FROM topics" in s]
    assert len(ours) == 2  # the page (with its aggregates) and the COUNT


# --- detail ----------------------------------------------------------------

def detail(admin, topic_id):
    res = admin.get(f"{LIST}/{topic_id}")
    assert res.status_code == 200, res.text
    return res.json()


def test_404(admin, session):
    assert admin.get(f"{LIST}/999").status_code == 404
    assert admin.get(f"{LIST}/x").status_code == 422


def test_detail_has_no_vote_support_front_or_state(admin, session):
    s1, s2 = make_sources(session, "Alpha", "Beta")
    t = make_topic(session, "Un sujet", [s1, s2])
    make_article(session, s1, "second", "Autre article", hours_ago=5, topic_id=t.id)
    session.commit()
    d = detail(admin, t.id)
    assert set(d) == {
        "id", "title", "summary", "first_seen_at", "updated_at", "article_count", "source_count", "articles",
        "articles_truncated", "approvals", "history",
    }
    assert (d["article_count"], d["source_count"]) == (3, 2)
    assert [a["title"] for a in d["articles"]][0].startswith("Un sujet")  # newest first
    assert len(d["articles"]) == 3 and d["articles_truncated"] is False
    assert d["articles"][0]["source"]["name"] in {"Alpha", "Beta"}


def test_topic_without_articles(admin, session):
    t = Topic(title="Vide")
    session.add(t)
    session.commit()
    d = detail(admin, t.id)
    assert d["articles"] == [] and d["article_count"] == 0 and d["source_count"] == 0


def test_detail_query_count_does_not_grow_with_data(admin, session):
    from app.db import get_engine

    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Requêtes", [s1, s2])
    session.commit()
    few = len(count_queries(get_engine(), lambda: admin.get(f"{LIST}/{t.id}")))
    for i in range(15):
        make_article(session, s1, f"more{i}", f"Article {i}", topic_id=t.id)
    session.commit()
    assert len(count_queries(get_engine(), lambda: admin.get(f"{LIST}/{t.id}"))) == few


def test_articles_of_a_topic_are_capped(admin, session, monkeypatch):
    from app.services import admin_topics

    monkeypatch.setattr(admin_topics, "MAX_TOPIC_ARTICLES", 2)
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Beaucoup", [s1, s2])
    make_article(session, s1, "x", "Encore", topic_id=t.id)
    session.commit()
    d = detail(admin, t.id)
    assert len(d["articles"]) == 2 and d["articles_truncated"] is True and d["article_count"] == 3


def test_no_personal_data_in_any_admin_response(admin, session):
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Confidentiel", [s1, s2])
    session.add(Account(email="secret0@private-mail.test"))
    session.commit()
    bodies = [
        admin.get(url).text
        for url in (
            "/api/admin/articles?page_size=200", "/api/admin/topics?page_size=200", f"/api/admin/topics/{t.id}",
            "/api/admin/sources", "/api/admin/stats", "/api/admin/edition/preview", "/api/admin/editions",
        )
    ]
    assert all(bodies)
    for body in bodies:
        assert "private-mail" not in body and "@example.org" not in body
        assert "email" not in body.lower() and "token" not in body.lower() and "hash" not in body.lower()

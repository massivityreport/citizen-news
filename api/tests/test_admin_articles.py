"""Back office: GET /api/admin/articles (server-side pagination, sort, filters)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.models import Article, MediaSource, Topic
from tests.test_admin_auth import PASSWORD

URL = "/api/admin/articles"
D = lambda day, hour=12: datetime(2026, 11, day, hour, tzinfo=UTC)  # noqa: E731


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


@pytest.fixture
def data(session):
    """3 sources (Beta inactive), 2 topics, 7 articles with known dates.
    ids: 1 Alpha/T-zeta/d1, 2 Alpha/-/d2, 3 Beta/T-alpha/d3, 4 Beta/T-alpha/d3(same date), 5 gamma/-/no date,
         6 gamma/T-zeta/d5, 7 Alpha/-/d5 23:59:59"""
    alpha, beta, gamma = (
        MediaSource(name="Alpha", feed_url="https://a.example/rss"),
        MediaSource(name="beta", feed_url="https://b.example/rss", active=False),
        MediaSource(name="Gamma", feed_url="https://c.example/rss"),
    )
    session.add_all([alpha, beta, gamma])
    t_zeta, t_alpha = Topic(title="Zeta"), Topic(title="alpha sujet")
    session.add_all([t_zeta, t_alpha])
    session.flush()
    rows = [
        (alpha, t_zeta, D(1)), (alpha, None, D(2)), (beta, t_alpha, D(3)), (beta, t_alpha, D(3)),
        (gamma, None, None), (gamma, t_zeta, D(5, 0)), (alpha, None, datetime(2026, 11, 5, 23, 59, 59, tzinfo=UTC)),
    ]
    for i, (source, topic, published) in enumerate(rows, 1):
        session.add(Article(
            source_id=source.id, url=f"https://x.example/{i}", title=f"Article {i}", published_at=published,
            topic_id=topic.id if topic else None,
        ))
    session.commit()
    return {"alpha": alpha.id, "beta": beta.id, "gamma": gamma.id, "zeta": t_zeta.id, "talpha": t_alpha.id}


def ids(res):
    assert res.status_code == 200, res.text
    return [a["id"] for a in res.json()["items"]]


# --- access ----------------------------------------------------------------

def test_requires_admin_session(client):
    assert client.get(URL).status_code == 401


def test_citizen_session_is_not_enough(logged):
    assert logged.get(URL).status_code == 401


# --- shape -----------------------------------------------------------------

def test_item_shape(admin, data):
    res = admin.get(URL, params={"sort": "date", "order": "asc"}).json()
    assert (res["total"], res["page"], res["page_size"]) == (7, 1, 50)
    first = res["items"][0]
    assert first == {
        "id": 1, "title": "Article 1", "url": "https://x.example/1", "published_at": "2026-11-01T12:00:00Z",
        "fetched_at": first["fetched_at"], "source": {"id": data["alpha"], "name": "Alpha", "active": True},
        "topic": {"id": data["zeta"], "title": "Zeta"}, "grouped": True,
    }
    ungrouped = next(a for a in res["items"] if a["id"] == 2)
    assert ungrouped["topic"] is None and ungrouped["grouped"] is False


def test_inactive_source_is_visible(admin, data):
    items = admin.get(URL, params={"source_id": data["beta"]}).json()["items"]
    assert len(items) == 2 and all(a["source"]["active"] is False for a in items)


# --- pagination ------------------------------------------------------------

def test_pagination(admin, data):
    pages = [admin.get(URL, params={"page": p, "page_size": 3, "sort": "date", "order": "asc"}).json() for p in (1, 2, 3)]
    assert [len(p["items"]) for p in pages] == [3, 3, 1]  # last page partial
    assert all(p["total"] == 7 for p in pages)
    seen = [a["id"] for p in pages for a in p["items"]]
    assert len(set(seen)) == 7


def test_page_out_of_range_is_empty_with_total(admin, data):
    res = admin.get(URL, params={"page": 9, "page_size": 3}).json()
    assert res["items"] == [] and res["total"] == 7 and res["page"] == 9


def test_empty_database(admin, session):
    assert admin.get(URL).json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": -1}, {"page": "x"}, {"page": 100_001}, {"page_size": 0}, {"page_size": 201}, {"page_size": "x"},
])
def test_bad_pagination_is_422(admin, params):
    assert admin.get(URL, params=params).status_code == 422


def test_max_page_size_is_accepted(admin, data):
    assert admin.get(URL, params={"page_size": 200}).json()["page_size"] == 200


# --- sort ------------------------------------------------------------------

@pytest.mark.parametrize("sort, order, expected", [
    # date: asc, nulls last; ties (3, 4) by id in the same direction
    ("date", "asc", [1, 2, 3, 4, 6, 7, 5]),
    ("date", "desc", [7, 6, 4, 3, 2, 1, 5]),
    # source (case-insensitive name): Alpha(1,2,7) beta(3,4) Gamma(5,6)
    ("source", "asc", [1, 2, 7, 3, 4, 5, 6]),
    ("source", "desc", [6, 5, 4, 3, 7, 2, 1]),
    # topic title (case-insensitive): "alpha sujet"(3,4) Zeta(1,6); ungrouped (2,5,7) last in both directions
    ("topic", "asc", [3, 4, 1, 6, 2, 5, 7]),
    ("topic", "desc", [6, 1, 4, 3, 7, 5, 2]),
])
def test_sorts_with_id_tie_break(admin, data, sort, order, expected):
    assert ids(admin.get(URL, params={"sort": sort, "order": order})) == expected


def test_default_sort_is_newest_first(admin, data):
    assert ids(admin.get(URL)) == [7, 6, 4, 3, 2, 1, 5]


def test_sort_is_stable_across_pages(admin, data):
    paged = [i for p in (1, 2, 3, 4) for i in ids(admin.get(URL, params={"sort": "topic", "page": p, "page_size": 2}))]
    assert paged == ids(admin.get(URL, params={"sort": "topic"}))


@pytest.mark.parametrize("params", [
    {"sort": "id"}, {"sort": "title; DROP TABLE articles"}, {"sort": "published_at"}, {"sort": ""},
    {"order": "up"}, {"order": "asc; --"}, {"sort": "date) desc, (select 1"},
])
def test_sort_outside_whitelist_is_422(admin, data, params):
    assert admin.get(URL, params=params).status_code == 422
    assert admin.get(URL).json()["total"] == 7  # nothing happened


# --- filters ---------------------------------------------------------------

def test_filter_by_topic(admin, data):
    assert sorted(ids(admin.get(URL, params={"topic_id": data["zeta"]}))) == [1, 6]


def test_filter_by_unknown_topic_is_empty(admin, data):
    assert admin.get(URL, params={"topic_id": 999}).json()["total"] == 0


def test_filter_by_source(admin, data):
    assert sorted(ids(admin.get(URL, params={"source_id": data["alpha"]}))) == [1, 2, 7]


def test_ungrouped(admin, data):
    res = admin.get(URL, params={"ungrouped": "true"}).json()
    assert sorted(a["id"] for a in res["items"]) == [2, 5, 7] and res["total"] == 3
    assert all(a["grouped"] is False for a in res["items"])


def test_ungrouped_false_is_no_filter(admin, data):
    assert admin.get(URL, params={"ungrouped": "false"}).json()["total"] == 7


def test_ungrouped_with_topic_id_is_422(admin, data):
    res = admin.get(URL, params={"ungrouped": "true", "topic_id": data["zeta"]})
    assert res.status_code == 422 and "s'excluent" in res.json()["detail"]


def test_date_bounds_are_inclusive_utc_days(admin, data):
    # date_from = 2026-11-03 (00:00 UTC included), date_to = 2026-11-05 (the whole day, 23:59:59 included)
    got = ids(admin.get(URL, params={"date_from": "2026-11-03", "date_to": "2026-11-05", "sort": "date", "order": "asc"}))
    assert got == [3, 4, 6, 7]  # article 5 has no date: excluded as soon as a date filter is set
    assert ids(admin.get(URL, params={"date_to": "2026-11-02", "sort": "date", "order": "asc"})) == [1, 2]
    assert ids(admin.get(URL, params={"date_from": "2026-11-05", "sort": "date", "order": "asc"})) == [6, 7]
    assert ids(admin.get(URL, params={"date_from": "2026-11-06"})) == []


def test_undated_article_appears_without_date_filter(admin, data):
    assert 5 in ids(admin.get(URL))


def test_single_day(admin, data):
    assert ids(admin.get(URL, params={"date_from": "2026-11-03", "date_to": "2026-11-03", "sort": "date"})) == [4, 3]


def test_filters_combine(admin, data):
    assert ids(admin.get(URL, params={"source_id": data["alpha"], "ungrouped": "true", "date_from": "2026-11-02"})) == [7, 2]
    assert ids(admin.get(URL, params={"source_id": data["beta"], "topic_id": data["talpha"]})) == [4, 3]
    assert ids(admin.get(URL, params={"source_id": data["gamma"], "topic_id": data["talpha"]})) == []
    res = admin.get(URL, params={"ungrouped": "true", "page": 2, "page_size": 2}).json()
    assert res["total"] == 3 and len(res["items"]) == 1


@pytest.mark.parametrize("params", [
    {"date_from": "2026-13-01"}, {"date_from": "yesterday"}, {"date_to": "2026-11-31"}, {"date_from": "2026-11-01T10:00:00"},
    {"date_from": "1999-12-31"}, {"date_to": "2101-01-01"}, {"date_to": "9999-12-31"}, {"date_from": "0001-01-01"},
    {"date_from": "2026-11-05", "date_to": "2026-11-04"}, {"date_from": ""}, {"topic_id": 0}, {"source_id": "x"},
    {"ungrouped": "maybe"},
])
def test_invalid_filters_are_422(admin, data, params):
    assert admin.get(URL, params=params).status_code == 422


# --- queries ---------------------------------------------------------------

def count_queries(engine, call):
    seen = []

    def on_execute(conn, cursor, statement, *a):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        call()
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
    return seen


def test_two_queries_whatever_the_page_size(admin, session, data):
    from app.db import get_engine

    admin.get(URL)  # authenticate path warmed up
    small = count_queries(get_engine(), lambda: admin.get(URL, params={"page_size": 1}))
    big = count_queries(get_engine(), lambda: admin.get(URL, params={"page_size": 200, "sort": "topic"}))
    queries = lambda stmts: [s for s in stmts if "FROM articles" in s]  # noqa: E731 (the session check is not ours)
    assert len(queries(small)) == len(queries(big)) == 2
    page = next(s for s in big if "LIMIT" in s and "FROM articles" in s)
    assert "JOIN media_sources" in page and "LEFT OUTER JOIN topics" in page


def test_filters_use_sql_not_python(admin, session, data):
    from app.db import get_engine

    stmts = count_queries(get_engine(), lambda: admin.get(URL, params={"topic_id": data["zeta"], "date_from": "2026-11-01"}))
    page = next(s for s in stmts if "LIMIT" in s and "FROM articles" in s)
    assert "articles.topic_id =" in page and "articles.published_at >=" in page

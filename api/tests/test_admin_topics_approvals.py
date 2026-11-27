"""Back office topics: approvals of the edition in progress, sort, and the history per published edition."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db import get_engine
from app.deps import clock
from app.models import Edition, EditionTopic, MediaSource
from app.services.edition_close import close_due_edition
from tests.helpers import make_accounts, make_sources, make_topic, put_une
from tests.test_admin_articles import count_queries
from tests.test_admin_auth import PASSWORD

LIST = "/api/admin/topics"
NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)  # winter: closing 16:00 UTC, edition in progress = 2026-11-27
TODAY = date(2026, 11, 27)


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    client.app.dependency_overrides[clock] = lambda: NOW
    return client


@pytest.fixture
def world(session):
    s = make_sources(session, "A", "B", "C")
    hot = make_topic(session, "Chaud", s[:2], hours_ago=5, now=NOW)
    mid = make_topic(session, "Moyen", s[:3], hours_ago=3, now=NOW)
    cold = make_topic(session, "Froid", s[:2], hours_ago=1, now=NOW)
    outside = make_topic(session, "Hors bassin", s[:1], hours_ago=2, now=NOW)  # one media only: not in the pool
    accounts = make_accounts(session, 3)
    put_une(session, accounts[0], TODAY, [hot.id, mid.id, outside.id])
    put_une(session, accounts[1], TODAY, [hot.id])
    put_une(session, accounts[2], date(2026, 11, 26), [cold.id])  # another day: not an approval of the current edition
    session.add(Edition(edition_date=date(2026, 11, 26), participants=1))  # published: the 27th is the one in progress
    session.commit()
    return hot.id, mid.id, cold.id, outside.id


def rows(admin, **params):
    return {i["id"]: i for i in admin.get(LIST, params=params).json()["items"]}


def test_approvals_are_the_selections_of_the_edition_in_progress(admin, world):
    hot, mid, cold, outside = world
    items = rows(admin)
    assert [items[t]["approvals"] for t in (hot, mid, cold)] == [2, 1, 0]
    assert items[outside]["approvals"] == 1  # the list is every topic, the pool does not filter it


def test_default_sort_is_approvals_desc(admin, world):
    hot, mid, cold, outside = world
    ids = [i["id"] for i in admin.get(LIST).json()["items"]]
    assert ids == [hot, outside, mid, cold]  # 2, then 1 and 1 (id desc breaks the tie), then 0


@pytest.mark.parametrize("sort, order, expected", [
    ("approvals", "asc", ["Froid", "Moyen", "Hors bassin", "Chaud"]),
    ("title", "asc", ["Chaud", "Froid", "Hors bassin", "Moyen"]),
    ("articles", "desc", ["Moyen", "Froid", "Chaud", "Hors bassin"]),
    ("updated", "desc", ["Froid", "Hors bassin", "Moyen", "Chaud"]),
])
def test_other_sorts(admin, world, sort, order, expected):
    items = admin.get(LIST, params={"sort": sort, "order": order}).json()["items"]
    assert [i["title"] for i in items] == expected


def test_after_closing_the_approvals_count_the_next_edition(admin, world, session):
    # the edition of the 27th is published: the edition in progress is the 28th (empty)
    after = datetime(2026, 11, 27, 16, 5, tzinfo=UTC)
    admin.app.dependency_overrides[clock] = lambda: after
    session.add(Edition(edition_date=TODAY, participants=0))
    session.commit()
    assert all(i["approvals"] == 0 for i in admin.get(LIST).json()["items"])


def test_query_count_is_constant(admin, world, session):
    small = len(count_queries(get_engine(), lambda: admin.get(LIST)))
    s = list(session.scalars(select(MediaSource)))
    accounts = make_accounts(session, 5)
    for n in range(15):
        t = make_topic(session, f"Plus {n}", s, now=NOW)
        for a in accounts:
            put_une(session, a, TODAY, [t.id])
    session.commit()
    assert len(count_queries(get_engine(), lambda: admin.get(LIST))) == small


# --- detail: current approvals and history ----------------------------------

def detail(admin, topic_id):
    r = admin.get(f"{LIST}/{topic_id}")
    assert r.status_code == 200
    return r.json()


def test_detail_has_current_approvals(admin, world):
    hot, mid, cold, outside = world
    assert detail(admin, hot)["approvals"] == 2
    assert detail(admin, cold)["approvals"] == 0
    assert detail(admin, hot)["history"] == []


def test_history_lists_published_editions_with_rank_or_null(admin, session):
    s = make_sources(session, "A", "B")
    day1, day2, day3 = date(2026, 11, 24), date(2026, 11, 25), date(2026, 11, 26)
    made = datetime(2026, 11, 25, 10, tzinfo=UTC)
    topics = [make_topic(session, f"T{i}", s, now=made) for i in range(11)]
    target = topics[10]
    a, b, c = make_accounts(session, 3)
    # day1 (published by hand, two participants): the target has 1 approval, outside the une of ten
    put_une(session, a, day1, [t.id for t in topics[:10]])
    put_une(session, b, day1, [t.id for t in topics[:10]] + [target.id])
    session.add(Edition(edition_date=day1, participants=2))
    # day2: the target alone, rank 1, 2 approvals of 2
    put_une(session, a, day2, [target.id])
    put_une(session, b, day2, [target.id])
    # day3: the target is not selected: no line
    put_une(session, c, day3, [topics[0].id])
    session.commit()
    for when in (datetime(2026, 11, 25, 16, tzinfo=UTC), datetime(2026, 11, 26, 16, tzinfo=UTC)):
        assert close_due_edition(session, when) is not None
    admin.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 26, 18, tzinfo=UTC)
    assert detail(admin, target.id)["history"] == [
        {"edition_date": "2026-11-25", "rank": 1, "approvals": 2, "proportion": 1.0},
        {"edition_date": "2026-11-24", "rank": None, "approvals": 1, "proportion": 0.5},
    ]
    assert [h["edition_date"] for h in detail(admin, topics[0].id)["history"]] == ["2026-11-26", "2026-11-24"]


def test_history_has_non_retained_approvals_from_the_selections(admin, session):
    s = make_sources(session, "A", "B")
    made = datetime(2026, 11, 25, 10, tzinfo=UTC)
    day = date(2026, 11, 25)
    topics = [make_topic(session, f"T{i}", s, now=made) for i in range(11)]
    accounts = make_accounts(session, 4)
    for acc in accounts[:3]:  # ten topics with 3 approvals each; the eleventh has 1
        put_une(session, acc, day, [t.id for t in topics[:10]])
    put_une(session, accounts[3], day, [topics[10].id])
    session.add(Edition(edition_date=date(2026, 11, 24), participants=0))
    session.commit()
    assert close_due_edition(session, datetime(2026, 11, 25, 16, tzinfo=UTC)) is not None
    admin.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 25, 18, tzinfo=UTC)
    assert detail(admin, topics[10].id)["history"] == [
        {"edition_date": "2026-11-25", "rank": None, "approvals": 1, "proportion": 0.25}
    ]
    assert detail(admin, topics[0].id)["history"][0]["rank"] == 1


def test_history_is_capped_to_the_30_latest_in_few_queries(admin, session):
    s = make_sources(session, "A", "B")
    t = make_topic(session, "Fidèle", s, now=NOW)
    (acc,) = make_accounts(session, 1)
    for n in range(35):
        day = date(2026, 10, 1) + timedelta(days=n)
        e = Edition(edition_date=day, participants=1)
        session.add(e)
        session.flush()
        session.add(EditionTopic(edition_id=e.id, rank=1, topic_id=t.id, title="x", summary="", sources=[], source_count=2,
                                 article_count=2, approvals=1, proportion=1.0, image_url=None))
    session.commit()
    h = detail(admin, t.id)["history"]
    assert len(h) == 30 and h[0]["edition_date"] == "2026-11-04" and h[-1]["edition_date"] == "2026-10-06"
    queries = count_queries(get_engine(), lambda: admin.get(f"{LIST}/{t.id}"))
    assert len(queries) <= 9


def test_nothing_personal(admin, world):
    from app.models import Account

    for url in (LIST, f"{LIST}/{world[0]}"):
        body = admin.get(url).text
        assert "@" not in body and "email" not in body.lower() and "account" not in body.lower()

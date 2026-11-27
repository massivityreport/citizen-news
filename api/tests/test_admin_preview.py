"""GET /api/admin/edition/preview: the same ranking as the closing, with ties and cut, and no write."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select, text

from app.db import get_engine
from app.deps import clock
from app.models import Edition, EditionTopic, MediaSource, Selection
from app.services import admin_editions, aggregation
from app.services.edition_close import close_due_edition
from tests.helpers import make_accounts, make_sources, make_topic, put_une
from tests.test_admin_articles import count_queries
from tests.test_admin_auth import PASSWORD

URL = "/api/admin/edition/preview"
NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)  # winter: closes at 16:00 UTC
DAY = date(2026, 11, 27)
CLOSING = datetime(2026, 11, 27, 16, 0, tzinfo=UTC)
ITEM_KEYS = {"rank", "topic_id", "title", "approvals", "proportion", "source_count", "article_count", "updated_at", "tied_with", "broken_by"}


@pytest.fixture
def admin(client, session):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    client.app.dependency_overrides[clock] = lambda: NOW
    session.add(Edition(edition_date=date(2026, 11, 26), participants=0))  # published: the 27th is the one in progress
    session.commit()
    return client


@pytest.fixture
def media(session):
    return make_sources(session, "A", "B", "C")


def topic(session, media, title, n=2, hours_ago=1.0, now=NOW):
    return make_topic(session, title, media[:n], hours_ago=hours_ago, now=now)


def approve(session, topics, counts, day=DAY):
    """counts[i] accounts approve topics[i] (accounts are shared: account j has topic i when j < counts[i])."""
    accounts = make_accounts(session, max(counts))
    for j, acc in enumerate(accounts):
        put_une(session, acc, day, [t.id for t, c in zip(topics, counts) if j < c])
    session.commit()
    return accounts


@pytest.fixture
def big(session, media):
    """14 topics: ranks 1-9 distinct, a tie at the cut (rank 10/11, by source_count), a tie by updated_at, one outside the pool."""
    ts = [topic(session, media, f"T{i}") for i in range(9)]
    t9 = topic(session, media, "T9", n=3)  # 3 media: wins the tie against T10
    t10 = topic(session, media, "T10", n=2)
    t11 = topic(session, media, "T11", hours_ago=5)
    t12 = topic(session, media, "T12", hours_ago=1)  # more recent: wins the tie against T11
    outside = topic(session, media, "Hors", n=1)  # one media: not eligible
    topics = ts + [t9, t10, t11, t12, outside]
    approve(session, topics, [14, 13, 12, 11, 10, 9, 8, 7, 6, 2, 2, 1, 1, 9])
    return topics


# --- access -------------------------------------------------------------------

def test_401_without_session(client):
    assert client.get(URL).status_code == 401


def test_401_with_citizen_session(logged):
    assert logged.get(URL).status_code == 401


# --- content ------------------------------------------------------------------

def test_headers_and_shape(admin, big):
    r = admin.get(URL)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store" and r.headers["x-robots-tag"] == "noindex"
    body = r.json()
    assert set(body) == {"computed_at", "edition_date", "participants", "topics", "next", "ties"}
    assert body["edition_date"] == "2026-11-27" and body["computed_at"] == "2026-11-27T10:00:00Z"
    assert body["participants"] == 14
    assert len(body["topics"]) == 10
    for item in body["topics"] + body["next"]:
        assert set(item) == ITEM_KEYS
    assert [i["rank"] for i in body["topics"]] == list(range(1, 11))
    first = body["topics"][0]
    assert (first["title"], first["approvals"], first["proportion"], first["source_count"], first["article_count"]) == ("T0", 14, 1.0, 2, 2)
    assert first["updated_at"].endswith("Z") and first["tied_with"] == [] and first["broken_by"] is None


def test_ranks_11_to_20_in_next_and_outside_pool_excluded(admin, big):
    body = admin.get(URL).json()
    assert [(i["rank"], i["title"]) for i in body["next"]] == [(11, "T10"), (12, "T12"), (13, "T11")]
    assert "Hors" not in admin.get(URL).text  # 9 approvals but one media only: not eligible, not shown


def test_next_is_capped_at_rank_20(admin, session, media):
    ts = [topic(session, media, f"S{i}", hours_ago=i / 10 + 0.1) for i in range(25)]
    approve(session, ts, [1] * 25)
    body = admin.get(URL).json()
    assert len(body["topics"]) == 10 and [i["rank"] for i in body["next"]] == list(range(11, 21))


def test_ties_cut_and_criteria(admin, big):
    body = admin.get(URL).json()
    t = {x.title: x.id for x in big}
    by_rank = {i["title"]: i for i in body["topics"] + body["next"]}
    assert by_rank["T9"]["tied_with"] == [t["T10"]] and by_rank["T9"]["broken_by"] == "source_count"
    assert by_rank["T10"]["tied_with"] == [t["T9"]] and by_rank["T10"]["rank"] == 11
    assert (by_rank["T12"]["rank"], by_rank["T11"]["rank"]) == (12, 13)
    assert by_rank["T12"]["broken_by"] == "updated_at" and by_rank["T12"]["tied_with"] == [t["T11"]]
    assert body["ties"] == [
        {"approvals": 2, "topic_ids": [t["T9"], t["T10"]], "broken_by": "source_count", "crosses_cut": True},
        {"approvals": 1, "topic_ids": [t["T12"], t["T11"]], "broken_by": "updated_at", "crosses_cut": False},
    ]


def test_tie_broken_by_id(admin, session, media):
    a, b = topic(session, media, "Un"), topic(session, media, "Deux")
    b.updated_at = a.updated_at
    session.commit()
    approve(session, [a, b], [1, 1])
    body = admin.get(URL).json()
    assert [i["topic_id"] for i in body["topics"]] == [a.id, b.id]
    assert body["ties"] == [{"approvals": 1, "topic_ids": [a.id, b.id], "broken_by": "id", "crosses_cut": False}]


def test_no_une_at_all(admin, media):
    body = admin.get(URL).json()
    assert (body["participants"], body["topics"], body["next"], body["ties"]) == (0, [], [], [])
    assert body["edition_date"] == "2026-11-27"


def test_an_account_with_an_empty_une_is_not_a_participant(admin, session, media):
    t = topic(session, media, "Seul")
    a, _empty = make_accounts(session, 2)  # the second has no selection row: an empty une
    put_une(session, a, DAY, [t.id])
    session.commit()
    body = admin.get(URL).json()
    assert body["participants"] == 1 and body["topics"][0]["proportion"] == 1.0


def test_edition_date_follows_the_calendar(admin, session, media):
    t = topic(session, media, "Tard", now=CLOSING)
    approve(session, [t], [1], day=DAY)
    admin.app.dependency_overrides[clock] = lambda: CLOSING  # closing passed, not published: still the 27th
    assert admin.get(URL).json()["edition_date"] == "2026-11-27"
    session.add(Edition(edition_date=DAY, participants=1))
    session.commit()
    admin.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 27, 16, 1, tzinfo=UTC)
    body = admin.get(URL).json()
    assert body["edition_date"] == "2026-11-28" and body["participants"] == 0


# --- the same function as the closing ----------------------------------------

def test_the_route_calls_aggregate(admin, big, monkeypatch):
    calls = []
    real = admin_editions.aggregate

    def spy(session, edition_date, now, **kw):
        calls.append((edition_date, now))
        return real(session, edition_date, now, **kw)

    monkeypatch.setattr(admin_editions, "aggregate", spy)
    assert admin.get(URL).status_code == 200
    assert calls == [(DAY, NOW)]
    assert admin_editions.aggregate is spy and real is aggregation.aggregate  # the very function of the closing


def test_the_same_inputs_give_the_ranking_the_closing_publishes(admin, session, big):
    admin.app.dependency_overrides[clock] = lambda: CLOSING
    body = admin.get(URL).json()
    edition = close_due_edition(session, CLOSING)
    published = session.scalars(select(EditionTopic).where(EditionTopic.edition_id == edition.id).order_by(EditionTopic.rank)).all()
    assert [(t["rank"], t["topic_id"], t["approvals"]) for t in body["topics"]] == [(p.rank, p.topic_id, p.approvals) for p in published]
    assert [round(t["proportion"], 3) for t in body["topics"]] == [round(p.proportion, 3) for p in published]
    assert body["participants"] == edition.participants
    assert [(t["title"], t["source_count"], t["article_count"]) for t in body["topics"]] == [(p.title, p.source_count, p.article_count) for p in published]


# --- no write -----------------------------------------------------------------

def snapshot(session):
    session.expire_all()
    return {
        name: session.execute(text(f"SELECT * FROM {name} ORDER BY 1")).all()
        for name in ("editions", "edition_topics", "selections", "topics", "articles")
    }


def test_nothing_is_written_and_the_closing_still_publishes(admin, session, big):
    admin.app.dependency_overrides[clock] = lambda: CLOSING
    before = snapshot(session)
    for _ in range(2):
        assert admin.get(URL).status_code == 200
    assert snapshot(session) == before
    assert session.scalar(select(func.count()).select_from(Edition).where(Edition.edition_date == DAY)) == 0
    edition = close_due_edition(session, CLOSING)  # no freeze: the closing publishes as usual
    assert edition is not None and edition.edition_date == DAY and edition.participants == 14
    assert session.scalar(select(func.count()).select_from(EditionTopic).where(EditionTopic.edition_id == edition.id)) == 10


def test_the_requests_are_executed_read_only(admin, big):
    statements = count_queries(get_engine(), lambda: admin.get(URL))
    assert not [s for s in statements if s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]


def test_constant_number_of_queries(admin, session, media):
    first = [topic(session, media, f"P{i}") for i in range(2)]
    approve(session, first, [2, 1])
    small = len(count_queries(get_engine(), lambda: admin.get(URL)))
    more = [topic(session, media, f"Q{i}", hours_ago=2 + i / 10) for i in range(25)]
    approve(session, more, [1] * 25, day=DAY)
    assert len(count_queries(get_engine(), lambda: admin.get(URL))) == small


def test_nothing_personal(admin, session, big):
    body = admin.get(URL).text
    assert "@" not in body and "example.org" not in body and "email" not in body.lower() and "account" not in body.lower()

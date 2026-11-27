"""Public edition routes, and: no approval counter reachable by a citizen before the publication."""

import re
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.deps import clock
from app.models.entities import Topic
from app.services.edition_close import close_due_edition
from tests.helpers import make_accounts, make_article, make_sources, make_topic, put_une

DAY = date(2026, 11, 27)
CLOSING = datetime(2026, 11, 27, 16, 0, tzinfo=UTC)  # 17:00 Paris, winter
BEFORE = CLOSING - timedelta(hours=6)
COUNTERS = re.compile(r"approval|proportion|participant|score|vote", re.I)


@pytest.fixture
def media(session):
    return make_sources(session, "A", "B", "C")


@pytest.fixture
def day_une(session, media):
    """Three citizens, two topics: Alpha 3 approvals (3 media), Beta 1."""
    a = make_topic(session, "Alpha", media, now=CLOSING)
    b = make_topic(session, "Beta", media[:2], now=CLOSING)
    x, y, z = make_accounts(session, 3)
    put_une(session, x, DAY, [a.id, b.id])
    put_une(session, y, DAY, [a.id])
    put_une(session, z, DAY, [a.id])
    session.commit()
    return a, b


@pytest.fixture
def published(session, client, day_une):
    client.app.dependency_overrides[clock] = lambda: CLOSING + timedelta(seconds=3)
    close_due_edition(session, CLOSING)
    return client


def test_current_is_null_before_the_first_edition(client):
    client.app.dependency_overrides[clock] = lambda: BEFORE
    r = client.get("/api/edition/current")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"edition": None, "next_close_at": "2026-11-27T16:00:00Z", "server_time": "2026-11-27T10:00:00Z"}


def test_current_edition_format(published, day_une):
    a, b = day_une
    r = published.get("/api/edition/current")
    body = r.json()
    assert (body["next_close_at"], body["server_time"]) == ("2026-11-28T16:00:00Z", "2026-11-27T16:00:03Z")
    edition = body["edition"]
    assert set(edition) == {"date", "published_at", "participants", "topics"}
    assert (edition["date"], edition["published_at"], edition["participants"]) == ("2026-11-27", "2026-11-27T16:00:00Z", 3)
    first, second = edition["topics"]
    assert set(first) == {
        "rank", "topic_id", "title", "summary", "sources", "source_count", "article_count", "approvals", "proportion", "image_url"
    }
    assert (first["rank"], first["topic_id"], first["title"], first["approvals"], first["proportion"]) == (1, a.id, "Alpha", 3, 1.0)
    assert (second["rank"], second["approvals"], second["proportion"]) == (2, 1, 0.333)
    assert first["source_count"] == 3 and len(first["sources"]) == 3
    assert set(first["sources"][0]) == {"name", "url", "title", "published_at"}


def test_next_close_after_closing_without_publication_is_tomorrow(client):
    client.app.dependency_overrides[clock] = lambda: CLOSING + timedelta(hours=1)  # worker late
    assert client.get("/api/edition/current").json()["next_close_at"] == "2026-11-28T16:00:00Z"


def test_edition_by_date_and_cache(published):
    r = published.get("/api/editions/2026-11-27")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=30"
    assert r.json() == published.get("/api/edition/current").json()["edition"]


def test_unknown_date_is_404_in_french(published):
    r = published.get("/api/editions/2026-11-26")
    assert (r.status_code, r.json()) == (404, {"detail": "Édition introuvable."})


@pytest.mark.parametrize("bad", ["abc", "2026-13-01", "2026-02-30", "20261127", "2026-1-2", "2026-11-27T10:00"])
def test_malformed_date_is_422(client, bad):
    r = client.get(f"/api/editions/{bad}")
    assert r.status_code == 422 and r.json()["detail"].startswith("Requête invalide")


def test_list_most_recent_first_with_limit(session, published, media):
    older = datetime(2026, 11, 28, 16, 0, tzinfo=UTC)
    make_topic(session, "Gamma", media, now=older)
    [acct] = make_accounts(session, 1)
    gamma = session.scalar(select(Topic).where(Topic.title == "Gamma"))
    put_une(session, acct, date(2026, 11, 28), [gamma.id])
    session.commit()
    assert close_due_edition(session, older) is not None
    r = published.get("/api/editions")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=30"
    items = r.json()["items"]
    assert [i["date"] for i in items] == ["2026-11-28", "2026-11-27"]
    assert set(items[1]) == {"date", "published_at", "participants", "topic_count"}
    assert (items[1]["participants"], items[1]["topic_count"]) == (3, 2)
    assert [i["date"] for i in published.get("/api/editions?limit=1").json()["items"]] == ["2026-11-28"]


@pytest.mark.parametrize("limit", ["0", "101", "x"])
def test_list_limit_bounds(client, limit):
    assert client.get(f"/api/editions?limit={limit}").status_code == 422


def test_list_is_empty_before_any_edition(client):
    assert client.get("/api/editions").json() == {"items": []}


def test_edition_is_frozen_for_the_api_too(session, published, day_une, media):
    a, _ = day_une
    before = published.get("/api/editions/2026-11-27").json()
    a.title = "Changé"
    make_article(session, media[2], "new", "Nouveau", hours_ago=0.1, now=CLOSING, topic_id=a.id)
    session.commit()
    assert published.get("/api/editions/2026-11-27").json() == before
    session.execute(delete(Topic).where(Topic.id == a.id))
    session.commit()
    after = published.get("/api/editions/2026-11-27").json()
    assert after["topics"][0]["topic_id"] is None and after["topics"][0]["title"] == "Alpha"
    assert after["topics"][1:] == before["topics"][1:]


def test_empty_edition_is_served(session, client, media):
    from app.models.entities import Edition

    session.add(Edition(edition_date=date(2026, 11, 26), participants=0))
    session.commit()
    client.app.dependency_overrides[clock] = lambda: CLOSING
    assert close_due_edition(session, CLOSING).participants == 0
    assert client.get("/api/editions/2026-11-27").json()["topics"] == []


def _citizen_calls(app, ids):
    """Every non-admin route of the application, with plausible parameters."""
    for route_path, operations in app.openapi()["paths"].items():  # every declared route (routers are wrapped)
        if route_path.startswith("/api/admin"):
            continue
        path = route_path.replace("{topic_id}", str(ids[0])).replace("{day}", "2026-11-27")
        for method in sorted(m.upper() for m in operations):
            kw = {}
            if path.endswith("/topics/pool"):
                path += "?seed=graine-0001"
            if method in ("PUT", "POST") and "/me/une" in path and not path.endswith(f"/topics/{ids[0]}"):
                kw["json"] = {"topic_ids": ids}
            elif method == "POST" and "magic-link" in path:
                kw["json"] = {"email": "x@example.org", "draft": {"topic_ids": ids}}
            elif method == "POST" and "verify" in path:
                kw["json"] = {"token": "nope"}
            yield method, path, kw


def test_no_counter_reachable_by_a_citizen_before_the_publication(session, logged, day_une, mails):
    from app.services.mailer import get_mailer

    logged.app.dependency_overrides[get_mailer] = lambda: mails
    logged.app.dependency_overrides[clock] = lambda: BEFORE
    ids = [t.id for t in day_une]
    visited = []
    for tab in ("random", "recent", "radar"):
        visited.append(("GET", f"/api/topics/pool?tab={tab}&seed=graine-0001"))
    visited += [(m, p) for m, p, _ in _citizen_calls(logged.app, ids)]
    for method, path, kw in _citizen_calls(logged.app, ids):
        r = logged.request(method, path, **kw)
        assert not COUNTERS.search(r.text), f"{method} {path} exposes a counter: {r.text[:200]}"
    for method, path in visited[:3]:
        r = logged.request(method, path)
        assert r.status_code == 200 and not COUNTERS.search(r.text)
    paths = {p.split("?")[0] for _, p in visited}
    assert {"/api/topics/pool", "/api/me/une", "/api/me/une/merge", "/api/edition/current", "/api/editions", "/api/editions/2026-11-27"} <= paths
    # Errors too: closed une, unknown topic, bad input.
    logged.app.dependency_overrides[clock] = lambda: CLOSING
    for r in (logged.put("/api/me/une/topics/1"), logged.put("/api/me/une/topics/999999"), logged.put("/api/me/une", json={"topic_ids": [0]})):
        assert not COUNTERS.search(r.text)

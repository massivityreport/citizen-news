"""Back office: list of published editions and one edition with its approvals."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.db import get_engine
from app.models import Edition, EditionTopic
from tests.test_admin_articles import count_queries
from tests.test_admin_auth import PASSWORD

LIST = "/api/admin/editions"


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


def publish(session, day, participants=4, topics=2):
    e = Edition(edition_date=day, participants=participants, published_at=datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=16))
    session.add(e)
    session.flush()
    for rank in range(1, topics + 1):
        session.add(EditionTopic(
            edition_id=e.id, rank=rank, topic_id=None, title=f"T{rank}", summary="Résumé", source_count=3, article_count=5,
            sources=[{"name": "A", "url": "https://a.example/1", "title": "Titre", "published_at": "2026-11-26T08:00:00Z"}],
            approvals=participants - rank + 1, proportion=(participants - rank + 1) / participants, image_url=None,
        ))
    session.flush()
    return e


@pytest.mark.parametrize("url", [LIST, f"{LIST}/2026-11-26"])
def test_401_without_session(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", [LIST, f"{LIST}/2026-11-26"])
def test_401_with_citizen_session(logged, url):
    assert logged.get(url).status_code == 401


def test_list_most_recent_first_with_counts(admin, session):
    publish(session, date(2026, 11, 25), participants=3, topics=1)
    publish(session, date(2026, 11, 26), participants=0, topics=0)
    publish(session, date(2026, 11, 27), participants=4, topics=2)
    session.commit()
    r = admin.get(LIST)
    assert r.headers["cache-control"] == "no-store" and r.headers["x-robots-tag"] == "noindex"
    body = r.json()
    assert (body["total"], body["page"], body["page_size"]) == (3, 1, 50)
    assert [(i["date"], i["participants"], i["topic_count"]) for i in body["items"]] == [
        ("2026-11-27", 4, 2), ("2026-11-26", 0, 0), ("2026-11-25", 3, 1),
    ]
    assert set(body["items"][0]) == {"date", "published_at", "participants", "topic_count"}
    assert body["items"][0]["published_at"] == "2026-11-27T16:00:00Z"


def test_list_empty(admin):
    assert admin.get(LIST).json() == {"items": [], "total": 0, "page": 1, "page_size": 50}


def test_pagination(admin, session):
    for n in range(5):
        publish(session, date(2026, 11, 20) + timedelta(days=n), topics=0)
    session.commit()
    page = admin.get(LIST, params={"page": 2, "page_size": 2}).json()
    assert [i["date"] for i in page["items"]] == ["2026-11-22", "2026-11-21"] and page["total"] == 5
    assert admin.get(LIST, params={"page": 9, "page_size": 2}).json()["items"] == []


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 201}, {"page": "x"}])
def test_pagination_422(admin, params):
    assert admin.get(LIST, params=params).status_code == 422


def test_list_query_count_is_constant(admin, session):
    publish(session, date(2026, 11, 1))
    session.commit()
    small = len(count_queries(get_engine(), lambda: admin.get(LIST)))
    for n in range(2, 20):
        publish(session, date(2026, 11, n))
    session.commit()
    assert len(count_queries(get_engine(), lambda: admin.get(LIST))) == small


def test_detail_is_the_full_edition_with_approvals(admin, session):
    publish(session, date(2026, 11, 26), participants=4, topics=2)
    session.commit()
    r = admin.get(f"{LIST}/2026-11-26")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"date", "published_at", "participants", "topics"}
    assert body["date"] == "2026-11-26" and body["participants"] == 4
    first = body["topics"][0]
    assert set(first) == {"rank", "topic_id", "title", "summary", "sources", "source_count", "article_count", "approvals", "proportion", "image_url"}
    assert (first["rank"], first["approvals"], first["proportion"]) == (1, 4, 1.0)
    assert body["topics"][1]["proportion"] == 0.75
    assert first["sources"][0] == {"name": "A", "url": "https://a.example/1", "title": "Titre", "published_at": "2026-11-26T08:00:00Z"}


def test_detail_same_shape_as_the_public_edition(admin, session):
    publish(session, date(2026, 11, 26))
    session.commit()
    assert admin.get(f"{LIST}/2026-11-26").json() == admin.get("/api/editions/2026-11-26").json()


def test_detail_404_and_422(admin):
    r = admin.get(f"{LIST}/2026-11-26")
    assert (r.status_code, r.json()) == (404, {"detail": "Édition introuvable."})
    assert admin.get(f"{LIST}/hier").status_code == 422
    assert admin.get(f"{LIST}/2026-13-45").status_code == 422


def test_nothing_personal(admin, session):
    publish(session, date(2026, 11, 26))
    session.commit()
    for url in (LIST, f"{LIST}/2026-11-26"):
        body = admin.get(url).text
        assert "@example" not in body and "email" not in body.lower() and "account" not in body.lower()

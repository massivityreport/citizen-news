"""Back-office opinions: list (newest first, unread filter, counter), detail, read / unread, delete."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import Feedback
from tests.test_admin_auth import PASSWORD

T0 = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
ACTIONS = [{"type": "page", "at": "2026-11-20T09:59:00Z", "page": "/"}, {"type": "login", "at": "2026-11-20T09:59:30Z"}]


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


def make(session, n, **over):
    f = Feedback(
        created_at=T0 + timedelta(hours=n), email=f"v{n}@example.org", kind="idea", message=f"Message {n} " + "x" * 300,
        page_name="Accueil", page_url="/?a=1", screen="390x844", browser="TestBrowser/1.0", recent_actions=None,
    )
    for k, v in over.items():
        setattr(f, k, v)
    session.add(f)
    session.commit()
    return f.id


def is_read(session, fid):
    session.expire_all()
    return session.get(Feedback, fid).is_read


# --- access -------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/admin/feedback"), ("GET", "/api/admin/feedback/unread-count"), ("GET", "/api/admin/feedback/1"),
    ("POST", "/api/admin/feedback/1/read"), ("POST", "/api/admin/feedback/1/unread"), ("DELETE", "/api/admin/feedback/1"),
])
def test_refused_without_admin_session(client, session, method, path):
    make(session, 1)
    assert client.request(method, path).status_code == 401
    assert session.scalar(select(func.count()).select_from(Feedback)) == 1


def test_citizen_session_is_refused(logged, session):
    fid = make(session, 1)
    assert logged.get("/api/admin/feedback").status_code == 401
    assert logged.delete(f"/api/admin/feedback/{fid}").status_code == 401


# --- list ---------------------------------------------------------------------

def test_list_is_newest_first_with_summary_fields(admin, session):
    old, new = make(session, 1), make(session, 2)
    body = admin.get("/api/admin/feedback").json()
    assert [i["id"] for i in body["items"]] == [new, old]
    assert (body["total"], body["unread_count"], body["page"]) == (2, 2, 1)
    item = body["items"][0]
    assert item["email"] == "v2@example.org" and item["kind"] == "idea"
    assert item["page_name"] == "Accueil" and item["page_url"] == "/?a=1"
    assert item["is_read"] is False and item["answered"] is False
    assert item["created_at"].startswith("2026-11-20T12:00:00")
    assert item["excerpt"].startswith("Message 2 xxx") and len(item["excerpt"]) <= 140
    assert "message" not in item and "recent_actions" not in item


def test_unread_filter_and_counter(admin, session):
    a, b, c = make(session, 1), make(session, 2), make(session, 3)
    session.get(Feedback, b).is_read = True
    session.commit()
    body = admin.get("/api/admin/feedback", params={"unread_only": True}).json()
    assert [i["id"] for i in body["items"]] == [c, a]
    assert body["total"] == 2 and body["unread_count"] == 2
    full = admin.get("/api/admin/feedback").json()
    assert full["total"] == 3 and full["unread_count"] == 2
    assert admin.get("/api/admin/feedback/unread-count").json() == {"unread_count": 2}


def test_list_is_paginated(admin, session):
    ids = [make(session, n) for n in range(1, 5)]
    body = admin.get("/api/admin/feedback", params={"page": 2, "page_size": 3}).json()
    assert [i["id"] for i in body["items"]] == [ids[0]] and body["total"] == 4


# --- detail, read / unread ----------------------------------------------------

def test_detail_has_everything_and_does_not_mark_read(admin, session):
    fid = make(session, 1, recent_actions=ACTIONS)
    body = admin.get(f"/api/admin/feedback/{fid}").json()
    assert body["message"].startswith("Message 1 ") and len(body["message"]) > 300
    assert (body["email"], body["page_name"], body["page_url"]) == ("v1@example.org", "Accueil", "/?a=1")
    assert (body["screen"], body["browser"], body["kind"]) == ("390x844", "TestBrowser/1.0", "idea")
    assert body["recent_actions"] == ACTIONS and body["answered"] is False
    assert is_read(session, fid) is False


def test_detail_without_journey(admin, session):
    fid = make(session, 1)
    assert admin.get(f"/api/admin/feedback/{fid}").json()["recent_actions"] is None


def test_mark_read_then_unread(admin, session):
    fid = make(session, 1)
    r = admin.post(f"/api/admin/feedback/{fid}/read")
    assert r.status_code == 200 and r.json()["is_read"] is True
    assert is_read(session, fid) is True
    assert admin.get("/api/admin/feedback/unread-count").json() == {"unread_count": 0}
    r = admin.post(f"/api/admin/feedback/{fid}/unread")
    assert r.status_code == 200 and r.json()["is_read"] is False
    assert is_read(session, fid) is False
    assert admin.get("/api/admin/feedback/unread-count").json() == {"unread_count": 1}


def test_mark_read_twice_is_harmless(admin, session):
    fid = make(session, 1)
    assert admin.post(f"/api/admin/feedback/{fid}/read").status_code == 200
    assert admin.post(f"/api/admin/feedback/{fid}/read").status_code == 200


# --- delete -------------------------------------------------------------------

def test_delete_removes_the_row_and_its_journey(admin, session):
    keep, gone = make(session, 1), make(session, 2, recent_actions=ACTIONS)
    assert admin.delete(f"/api/admin/feedback/{gone}").status_code == 204
    session.expire_all()
    assert [f.id for f in session.scalars(select(Feedback))] == [keep]
    assert admin.get(f"/api/admin/feedback/{gone}").status_code == 404
    assert admin.get("/api/admin/feedback/unread-count").json() == {"unread_count": 1}


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("POST", "/read"), ("POST", "/unread"), ("DELETE", "")])
def test_unknown_id_is_404(admin, method, suffix):
    r = admin.request(method, f"/api/admin/feedback/999{suffix}")
    assert r.status_code == 404 and isinstance(r.json()["detail"], str)

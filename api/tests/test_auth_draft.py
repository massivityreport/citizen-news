"""Magic link with a draft une: POST /api/auth/magic-link {draft} and POST /api/auth/verify merge."""

import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.deps import clock
from app.main import create_app
from app.models.entities import Account, Edition, LoginToken, Selection
from app.services import auth, une
from tests.helpers import ask, make_sources, make_topic

NOW = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)  # open; closes 16:00 UTC
DAY = date(2026, 11, 27)
EMAIL = "a@example.org"
ME = "/api/me/une"


@pytest.fixture(autouse=True)
def pinned(api):
    api.app.dependency_overrides[clock] = lambda: NOW


@pytest.fixture
def ids(session):
    media = make_sources(session, "A", "B")
    out = [make_topic(session, f"T{i}", media, hours_ago=1 + i / 10, now=NOW).id for i in range(12)]
    out.append(make_topic(session, "vieux", media, hours_ago=30, now=NOW).id)  # outside the pool: ids[12]
    session.commit()
    return out


def login(api, mails, draft=None, email=EMAIL):
    """Request a link (with a draft), then verify it from a FRESH browser (no cookies of `api`)."""
    body = {"email": email} | ({"draft": draft} if draft is not None else {})
    assert api.post("/api/auth/magic-link", json=body).status_code == 202
    browser = TestClient(api.app)
    return browser, browser.post("/api/auth/verify", json={"token": mails.last_token()})


def stored_draft(session):
    session.expire_all()
    return session.scalars(select(LoginToken.draft).order_by(LoginToken.id.desc())).first()


# --- request ---

def test_request_with_draft_answers_202_like_without(api, mails, ids):
    plain = ask(api)
    withdraft = api.post("/api/auth/magic-link", json={"email": "b@example.org", "draft": {"topic_ids": ids[:2]}})
    assert (plain.status_code, plain.json()) == (withdraft.status_code, withdraft.json()) == (202, {})
    assert plain.headers.keys() == withdraft.headers.keys()


def test_answer_is_identical_whether_the_account_exists_or_not(api, session, ids):
    session.add(Account(email="known@example.org"))
    session.commit()
    draft = {"topic_ids": ids[:3]}
    known = api.post("/api/auth/magic-link", json={"email": "known@example.org", "draft": draft})
    unknown = api.post("/api/auth/magic-link", json={"email": "unknown@example.org", "draft": draft})
    assert (known.status_code, known.content) == (unknown.status_code, unknown.content) == (202, b"{}")


def test_draft_is_stored_deduplicated_with_the_token(api, session, ids):
    api.post("/api/auth/magic-link", json={"email": EMAIL, "draft": {"topic_ids": [ids[3], ids[1], ids[3]]}})
    assert stored_draft(session) == {"topic_ids": [ids[3], ids[1]]}


def test_no_draft_or_empty_draft_stores_nothing(api, session):
    api.post("/api/auth/magic-link", json={"email": EMAIL})
    assert stored_draft(session) is None
    api.post("/api/auth/magic-link", json={"email": EMAIL, "draft": {"topic_ids": []}})
    assert stored_draft(session) is None


def test_ten_topics_accepted_eleven_refused(api, ids):
    assert api.post("/api/auth/magic-link", json={"email": EMAIL, "draft": {"topic_ids": ids[:10]}}).status_code == 202
    r = api.post("/api/auth/magic-link", json={"email": EMAIL, "draft": {"topic_ids": ids[:11]}})
    assert r.status_code == 422 and "detail" in r.json()


@pytest.mark.parametrize("draft", [{"topic_ids": [0]}, {"topic_ids": [-3]}, {"topic_ids": ["x"]}, {"topic_ids": [1.5]},
                                   {"topic_ids": "1"}, {}, {"topic_ids": [2**40]}, "texte", {"topic_ids": list(range(1, 300))}])
def test_invalid_drafts_are_422(api, draft):
    assert api.post("/api/auth/magic-link", json={"email": EMAIL, "draft": draft}).status_code == 422


def test_draft_never_appears_in_the_link_the_mail_or_the_logs(api, mails, ids, caplog):
    caplog.set_level(logging.DEBUG)
    api.post("/api/auth/magic-link", json={"email": EMAIL, "draft": {"topic_ids": ids[:3]}})
    api.post("/api/auth/magic-link", json={"email": "c@example.org", "draft": {"topic_ids": ids[:11]}})  # 422
    link = [line for line in mails.sent[-1][2].split() if "connexion" in line][0]
    assert link.endswith("/connexion?token=" + mails.last_token())  # only the token
    assert "draft" not in mails.sent[-1][2] and "topic" not in mails.sent[-1][2].lower()
    assert "draft" not in caplog.text.lower() and "topic_ids" not in caplog.text


# --- verify ---

def test_verify_merges_the_draft_even_from_another_browser(api, mails, ids, session):
    browser, r = login(api, mails, {"topic_ids": [ids[2], ids[0], ids[12], 99999]})
    assert r.status_code == 200
    assert r.json() == {"email": EMAIL, "draft": {"added": 2, "ignored": 2}}  # out of the pool + unknown
    assert browser.get(ME).json()["topic_ids"] == [ids[2], ids[0]]  # same une through the new session
    assert r.headers["cache-control"] == "no-store"


def test_verify_without_draft_answers_null_and_leaves_the_une_empty(api, mails, ids):
    browser, r = login(api, mails)
    assert r.json() == {"email": EMAIL, "draft": None}
    assert browser.get(ME).json()["topic_ids"] == []


def test_draft_never_overwrites_an_existing_une(api, mails, ids, session):
    account = Account(email=EMAIL)
    session.add(account)
    session.commit()
    for t in ids[:9]:
        une.add_topic(session, account.id, t, NOW)
    browser, r = login(api, mails, {"topic_ids": [ids[0], ids[10], ids[11]]})
    assert r.json()["draft"] == {"added": 1, "ignored": 1}  # one place left; ids[0] is already there
    assert browser.get(ME).json()["topic_ids"] == ids[:9] + [ids[10]]


def test_closed_edition_drops_the_draft_and_writes_nothing(api, mails, ids, session):
    api.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 27, 16, 5, tzinfo=UTC)
    browser, r = login(api, mails, {"topic_ids": ids[:3]})
    assert r.status_code == 200 and r.json() == {"email": EMAIL, "draft": None}
    assert "cn_session" in r.cookies or browser.get("/api/me").status_code == 200  # login itself works
    assert session.scalar(select(Selection.id)) is None


def test_after_publication_the_draft_goes_to_the_next_edition(api, mails, ids, session):
    api.app.dependency_overrides[clock] = lambda: datetime(2026, 11, 27, 16, 5, tzinfo=UTC)
    session.add(Edition(edition_date=DAY, participants=0))
    session.commit()
    browser, r = login(api, mails, {"topic_ids": ids[:2]})
    assert r.json()["draft"] == {"added": 2, "ignored": 0}
    assert browser.get(ME).json()["edition_date"] == "2026-11-28"


def test_draft_is_erased_when_the_token_is_consumed(api, mails, ids, session):
    browser, r = login(api, mails, {"topic_ids": ids[:3]})
    assert r.status_code == 200
    session.expire_all()
    row = session.scalars(select(LoginToken)).one()
    assert row.draft is None and row.used_at is not None
    # the same link cannot replay the draft
    again = browser.post("/api/auth/verify", json={"token": mails.last_token()})
    assert again.status_code == 400


def test_invalid_token_does_not_touch_anything(api, ids, session):
    api.post("/api/auth/magic-link", json={"email": EMAIL, "draft": {"topic_ids": ids[:2]}})
    assert api.post("/api/auth/verify", json={"token": "faux"}).status_code == 400
    assert stored_draft(session) == {"topic_ids": ids[:2]}
    assert session.scalar(select(Selection.id)) is None


def test_expired_token_loses_its_draft_then_the_row(session, ids):
    token = auth.create_login_token(session, EMAIL, at=NOW - timedelta(hours=1), draft_topic_ids=ids[:2])
    assert auth.consume_login_token(session, token, at=NOW) is None  # expired
    auth.purge_expired(session, at=NOW)
    assert session.scalars(select(LoginToken.draft)).all() == [None]  # draft forgotten at once
    auth.purge_expired(session, at=NOW + timedelta(days=2))
    assert session.scalars(select(LoginToken)).all() == []


def test_consume_returns_email_and_draft_once(session, ids):
    token = auth.create_login_token(session, EMAIL, draft_topic_ids=ids[:2])
    assert auth.consume_login_token(session, token) == (EMAIL, ids[:2])
    assert auth.consume_login_token(session, token) is None


def test_a_merge_failure_does_not_block_the_login(api, mails, ids, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("topic_ids " + str(ids[:2]))

    monkeypatch.setattr(une, "merge", boom)
    browser, r = login(api, mails, {"topic_ids": ids[:2]})
    assert r.status_code == 200 and r.json()["draft"] is None
    assert browser.get("/api/me").status_code == 200

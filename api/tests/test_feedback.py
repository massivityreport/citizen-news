import pytest
from sqlalchemy import select

from app.models import Feedback
from app.services.ratelimit import get_rate_limiter
from config.settings import get_settings

PAYLOAD = {
    "kind": "problem",
    "message": "Le bouton ne répond pas",
    "email": "visiteur@example.org",
    "page_name": "Accueil",
    "page_url": "/une/2026-11-26?x=1",
    "screen": "390x844",
}


def send(api, **over):
    body = {**PAYLOAD, **over}
    body = {k: v for k, v in body.items() if v is not None}
    return api.post("/api/feedback", json=body, headers={"User-Agent": "TestBrowser/1.0"})


def rows(session):
    session.expire_all()
    return list(session.scalars(select(Feedback)))


def test_anonymous_feedback_is_stored(api, session):
    r = send(api, email=" Visiteur@Example.org ")
    assert r.status_code == 201
    [f] = rows(session)
    assert (f.email, f.kind, f.message) == ("visiteur@example.org", "problem", "Le bouton ne répond pas")
    assert (f.page_name, f.page_url, f.screen, f.browser) == ("Accueil", "/une/2026-11-26?x=1", "390x844", "TestBrowser/1.0")
    assert f.recent_actions is None


def test_logged_in_uses_session_email_not_the_client_one(logged, session):
    r = send(logged, email="usurpe@example.org")
    assert r.status_code == 201
    assert rows(session)[0].email == "a@example.org"


def test_logged_in_needs_no_email(logged, session):
    assert send(logged, email=None).status_code == 201
    assert rows(session)[0].email == "a@example.org"


@pytest.mark.parametrize("email", [None, "", "pas-un-email", "a@b", "a b@example.org", "x" * 250 + "@example.org"])
def test_invalid_or_missing_email_is_refused(api, session, email):
    assert send(api, email=email).status_code == 422
    assert rows(session) == []


def test_message_too_long_is_refused_and_2000_accepted(api, session):
    assert send(api, message="a" * 2001).status_code == 422
    assert rows(session) == []
    assert send(api, message="a" * 2000).status_code == 201


@pytest.mark.parametrize("message", ["", "   \n "])
def test_empty_message_is_refused(api, session, message):
    assert send(api, message=message).status_code == 422


def test_kind_must_be_known(api):
    assert send(api, kind="spam").status_code == 422
    assert send(api, kind="idea").status_code == 201
    assert send(api, kind="other").status_code == 201


@pytest.mark.parametrize("field,value", [("screen", "<script>"), ("screen", "99999x1"), ("page_url", "x" * 501), ("page_name", "x" * 201)])
def test_context_fields_are_validated(api, field, value):
    assert send(api, **{field: value}).status_code == 422


def test_message_is_stored_verbatim_and_sql_is_parameterised(api, session):
    nasty = "<img src=x onerror=alert(1)>'); DROP TABLE feedback;--"
    assert send(api, message=nasty).status_code == 201
    assert rows(session)[0].message == nasty


def test_rate_limit_per_email(api, session):
    for i in range(5):
        assert send(api).status_code == 201
    r = send(api)
    assert r.status_code == 429 and "Retry-After" in r.headers
    assert len(rows(session)) == 5
    assert send(api, email="autre@example.org").status_code == 201


def test_rate_limit_per_device(api, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_FEEDBACK_PER_IP", "2")
    get_settings.cache_clear()
    try:
        assert [send(api, email=f"u{i}@example.org").status_code for i in range(3)] == [201, 201, 429]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_logged_in_limit_is_keyed_on_session_email(logged):
    codes = [send(logged, email=f"u{i}@example.org").status_code for i in range(6)]
    assert codes == [201] * 5 + [429]


def test_invalid_requests_do_not_use_the_quota(api):
    for _ in range(10):
        send(api, message="")
    assert send(api).status_code == 201


def action(i=0, **over):
    return {"type": "page", "at": f"2026-11-27T10:{i % 60:02d}:00.000Z", "page": f"/archives?p={i}", **over}


def test_recent_actions_are_stored(api, session):
    actions = [action(0), {"type": "topic_added", "at": "2026-11-27T10:01:00.000Z", "topic_id": 12},
               {"type": "topic_removed", "at": "2026-11-27T10:02:00.000Z", "topic_id": 12},
               {"type": "login", "at": "2026-11-27T10:03:00.000Z"}]
    assert send(api, recent_actions=actions).status_code == 201
    assert rows(session)[0].recent_actions == actions


def test_recent_actions_absent_or_empty(api, session):
    assert send(api).status_code == 201
    assert send(api, recent_actions=[], email="b@example.org").status_code == 201
    assert [f.recent_actions for f in rows(session)] == [None, []]


def test_twenty_actions_accepted_twenty_one_refused(api, session):
    assert send(api, recent_actions=[action(i) for i in range(20)]).status_code == 201
    assert len(rows(session)[0].recent_actions) == 20
    assert send(api, recent_actions=[action(i) for i in range(21)], email="b@example.org").status_code == 422
    assert len(rows(session)) == 1


@pytest.mark.parametrize("bad", [
    "pas un tableau", {"type": "page"},
    [{"type": "inconnu", "at": "2026-11-27T10:00:00Z"}],
    [{"type": "page", "at": "x" * 41, "page": "/"}],
    [{"type": "page", "at": "2026-11-27T10:00:00Z", "page": "x" * 501}],
    [{"type": "page", "at": "2026-11-27T10:00:00Z"}],
    [{"type": "topic_added", "at": "2026-11-27T10:00:00Z"}],
    [{"type": "login", "at": "2026-11-27T10:00:00Z", "autre": "champ"}],
    [{"type": "page", "at": "2026-11-27T10:00:00Z", "page": "/a\nb"}],
    ["texte"],
])
def test_invalid_recent_actions_are_refused(api, session, bad):
    assert send(api, recent_actions=bad).status_code == 422
    assert rows(session) == []

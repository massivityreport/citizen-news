import re
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.deps import SESSION_COOKIE
from app.models import Account, AuthSession, LoginToken
from app.services import auth
from app.services.mailer import get_mailer
from tests.helpers import ask


def test_magic_link_same_answer_for_known_and_unknown(api, mails, session):
    session.add(Account(email="known@example.org"))
    session.commit()
    known, unknown = ask(api, "known@example.org"), ask(api, "unknown@example.org")
    assert (known.status_code, known.json()) == (unknown.status_code, unknown.json()) == (202, {})
    assert [m[0] for m in mails.sent] == ["known@example.org", "unknown@example.org"]
    assert session.scalar(select(func.count()).select_from(Account)) == 1  # no account created yet


def test_magic_link_normalizes_email(api, mails, session):
    assert ask(api, "  Alice@Example.ORG ").status_code == 202
    assert mails.sent[0][0] == "alice@example.org"
    assert session.scalars(select(LoginToken.email)).one() == "alice@example.org"


@pytest.mark.parametrize("bad", ["", "nope", "a@b", "a b@c.org", "a@@c.org", "a@c..org", "x" * 250 + "@c.org", 12])
def test_magic_link_rejects_bad_email(api, mails, bad):
    r = api.post("/api/auth/magic-link", json={"email": bad})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert not mails.sent


def test_magic_link_stores_only_the_hash_and_mails_the_link(api, mails, session):
    ask(api)
    token = mails.last_token()
    row = session.scalars(select(LoginToken)).one()
    assert row.token_hash == auth.hash_token(token) and token not in row.token_hash
    assert row.used_at is None and len(token) >= 40
    assert f"http://localhost:5173/connexion?token={token}" in mails.sent[0][2]
    delta = row.expires_at - auth.now()
    assert timedelta(minutes=14) < delta <= timedelta(minutes=15)


def test_magic_link_mail_failure_is_invisible(api, mails):
    class Broken:
        def send(self, *a):
            raise OSError("smtp down")

    api.app.dependency_overrides[get_mailer] = lambda: Broken()
    r = ask(api)
    assert (r.status_code, r.json()) == (202, {})


def test_verify_success_sets_cookie_and_creates_account(api, mails, session):
    ask(api)
    r = api.post("/api/auth/verify", json={"token": mails.last_token()})
    assert (r.status_code, r.json()) == (200, {"email": "a@example.org"})
    cookie = r.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "secure" not in cookie.replace("samesite", "")  # COOKIE_SECURE defaults to false
    assert f"max-age={30 * 86400}" in cookie
    assert session.scalar(select(func.count()).select_from(Account)) == 1
    assert api.get("/api/me").json() == {"email": "a@example.org"}


def test_cookie_secure_when_configured(api, mails, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("MAIL_BACKEND", "smtp")  # console is refused with COOKIE_SECURE=true
    monkeypatch.setenv("ADMIN_PASSWORD", "un-vrai-secret-long")  # the dev default is refused with COOKIE_SECURE=true
    monkeypatch.setenv("SMTP_HOST", "mail.test")
    get_settings.cache_clear()
    try:
        ask(api)
        r = api.post("/api/auth/verify", json={"token": mails.last_token()})
        assert "; secure" in r.headers["set-cookie"].lower()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_verify_token_is_single_use(api, mails):
    ask(api)
    token = mails.last_token()
    assert api.post("/api/auth/verify", json={"token": token}).status_code == 200
    again = api.post("/api/auth/verify", json={"token": token})
    assert again.status_code == 400 and again.json() == {"detail": "Lien de connexion invalide ou expiré"}


def test_verify_invalid_token(api):
    r = api.post("/api/auth/verify", json={"token": "n'importe quoi"})
    assert r.status_code == 400 and "Set-Cookie" not in r.headers


def test_verify_expired_token(api, mails, session):
    ask(api)
    session.execute(LoginToken.__table__.update().values(expires_at=auth.now() - timedelta(seconds=1)))
    session.commit()
    r = api.post("/api/auth/verify", json={"token": mails.last_token()})
    assert r.status_code == 400 and "Set-Cookie" not in r.headers
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_two_links_same_email_create_one_account(api, mails, session):
    ask(api)
    ask(api, "A@example.org")
    first, second = (t for t in [re.search(r"token=([\w-]+)", m[2]).group(1) for m in mails.sent])
    assert api.post("/api/auth/verify", json={"token": first}).status_code == 200
    assert api.post("/api/auth/verify", json={"token": second}).status_code == 200
    assert session.scalar(select(func.count()).select_from(Account)) == 1
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 2


def test_me_requires_session(api):
    r = api.get("/api/me")
    assert r.status_code == 401 and isinstance(r.json()["detail"], str)


def test_logout_revokes_session_and_clears_cookie(api, mails, session):
    ask(api)
    api.post("/api/auth/verify", json={"token": mails.last_token()})
    stolen = api.cookies.get(SESSION_COOKIE)
    r = api.post("/api/auth/logout")
    assert r.status_code == 204
    assert "max-age=0" in r.headers["set-cookie"].lower() or "expires" in r.headers["set-cookie"].lower()
    assert api.get("/api/me").status_code == 401
    api.cookies.set(SESSION_COOKIE, stolen)
    assert api.get("/api/me").status_code == 401  # revoked server-side, not only cleared
    assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_logout_without_session_is_idempotent(api):
    assert api.post("/api/auth/logout").status_code == 204


def test_magic_link_purges_expired_tokens(api, session):
    ask(api, "old@example.org")
    session.execute(LoginToken.__table__.update().values(expires_at=auth.now() - timedelta(days=2)))
    session.commit()
    ask(api, "new@example.org")
    assert session.scalars(select(LoginToken.email)).all() == ["new@example.org"]


def test_mail_failure_does_not_log_token_or_address(api, caplog):
    import logging

    class Leaky:
        def send(self, to, subject, body):
            raise RuntimeError(f"SMTP refused {to}: {body}")

    api.app.dependency_overrides[get_mailer] = lambda: Leaky()
    with caplog.at_level(logging.DEBUG):
        r = ask(api, "secret.person@example.org")
    assert r.status_code == 202
    assert "secret.person" not in caplog.text and "token=" not in caplog.text
    assert any(rec.levelno == logging.ERROR for rec in caplog.records)  # the failure is still reported

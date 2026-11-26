import logging
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.deps import ADMIN_COOKIE, SESSION_COOKIE
from app.models import AdminSession
from app.services import admin as admin_service
from app.services import auth
from config.settings import DEFAULT_ADMIN_PASSWORD, Settings, get_settings

PASSWORD = "make-media-great-again"


@pytest.fixture
def admin(client):
    r = client.post("/api/admin/login", json={"password": PASSWORD})
    assert r.status_code == 200
    return client


def login(client, password=PASSWORD):
    return client.post("/api/admin/login", json={"password": password})


def reload_settings(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _restore_settings():
    yield
    get_settings.cache_clear()


# --- access -----------------------------------------------------------------

def test_me_requires_a_cookie(client):
    r = client.get("/api/admin/me")
    assert r.status_code == 401 and isinstance(r.json()["detail"], str)


def test_me_rejects_invalid_cookie(client):
    client.cookies.set(ADMIN_COOKIE, "nope", path="/api/admin")
    assert client.get("/api/admin/me").status_code == 401


def test_me_rejects_expired_session(admin, session):
    row = session.scalars(select(AdminSession)).one()
    row.expires_at = auth.now() - timedelta(seconds=1)
    session.commit()
    assert admin.get("/api/admin/me").status_code == 401


def test_citizen_session_gives_no_admin_access(logged):
    assert logged.get("/api/admin/me").status_code == 401
    logged.cookies.set(ADMIN_COOKIE, logged.cookies.get(SESSION_COOKIE), path="/api/admin")
    assert logged.get("/api/admin/me").status_code == 401  # same token under the admin cookie name: unknown hash


def test_admin_cookie_gives_no_citizen_access(admin):
    assert admin.get("/api/me").status_code == 401
    assert admin.post("/api/votes", json={"topic_id": 1, "choice": "more"}).status_code == 401
    assert admin.get("/api/votes/mine").status_code == 401


def test_all_admin_routes_except_login_and_logout_are_protected(client):
    from app.routers.admin import protected

    assert protected.routes  # at least /me
    for route in client.app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/admin") and path not in ("/api/admin/login", "/api/admin/logout"):
            for method in route.methods:
                assert client.request(method, path).status_code == 401, (method, path)


# --- login / logout ---------------------------------------------------------

def test_login_ok_sets_cookie_and_me_works(client):
    r = login(client)
    assert r.status_code == 200 and r.json() == {"authenticated": True}
    cookie = r.headers["set-cookie"].lower()
    assert ADMIN_COOKIE in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/api/admin" in cookie and f"max-age={8 * 3600}" in cookie and "secure" not in cookie
    assert client.get("/api/admin/me").json() == {"authenticated": True}


def test_login_wrong_password(client, session):
    for bad in ["", "wrong", PASSWORD + "x", "é" * 10]:
        r = login(client, bad)
        assert r.status_code == 401 and r.json() == {"detail": "Mot de passe incorrect"}
        assert "set-cookie" not in r.headers
    assert session.scalars(select(AdminSession)).all() == []


def test_login_rejects_malformed_body(client):
    assert client.post("/api/admin/login", json={}).status_code == 422
    assert client.post("/api/admin/login", json={"password": "x" * 2000}).status_code == 422


def test_only_the_hash_is_stored(admin, session):
    token = admin.cookies.get(ADMIN_COOKIE)
    row = session.scalars(select(AdminSession)).one()
    assert row.token_hash == auth.hash_token(token) and token != row.token_hash
    assert PASSWORD not in row.token_hash


def test_login_purges_expired_sessions(client, session):
    old = AdminSession(token_hash="a" * 64, expires_at=auth.now() - timedelta(hours=1))
    session.add(old)
    session.commit()
    login(client)
    hashes = session.scalars(select(AdminSession.token_hash)).all()
    assert "a" * 64 not in hashes and len(hashes) == 1


def test_session_duration_is_configurable(client, monkeypatch):
    reload_settings(monkeypatch, ADMIN_SESSION_HOURS="2")
    assert "max-age=7200" in login(client).headers["set-cookie"].lower()


def test_cookie_secure_with_cookie_secure_setting(client, monkeypatch):
    reload_settings(monkeypatch, COOKIE_SECURE="true", ADMIN_PASSWORD="un-autre-mot-de-passe", MAIL_BACKEND="smtp", SMTP_HOST="x")
    r = login(client, "un-autre-mot-de-passe")
    assert r.status_code == 200 and "; secure" in r.headers["set-cookie"].lower()


def test_logout_invalidates_session_and_clears_cookie(admin, session):
    r = admin.post("/api/admin/logout")
    assert r.status_code == 204
    cookie = r.headers["set-cookie"].lower()
    assert ADMIN_COOKIE in cookie and "max-age=0" in cookie and "path=/api/admin" in cookie
    assert session.scalars(select(AdminSession)).all() == []
    # the old token is dead even if a client kept it
    admin.cookies.set(ADMIN_COOKIE, "stale", path="/api/admin")
    assert admin.get("/api/admin/me").status_code == 401


def test_logout_without_session_is_harmless(client):
    assert client.post("/api/admin/logout").status_code == 204


def test_login_is_rate_limited_per_ip(client, monkeypatch):
    reload_settings(monkeypatch, RATE_LIMIT_ADMIN_LOGIN_PER_IP="3")
    assert [login(client, "bad").status_code for _ in range(3)] == [401] * 3
    r = login(client, PASSWORD)  # even the right password is refused once over the limit
    assert r.status_code == 429 and 1 <= int(r.headers["Retry-After"]) <= 900
    assert isinstance(r.json()["detail"], str)


def test_admin_responses_are_private(client, admin):
    for r in (client.get("/api/admin/me"), login(client, "bad"), client.post("/api/admin/logout")):
        assert r.headers["cache-control"] == "no-store" and r.headers["x-robots-tag"] == "noindex"
    assert "no-store" not in client.get("/api/health").headers.get("cache-control", "")


def test_password_never_in_logs_or_responses(client, caplog):
    with caplog.at_level(logging.DEBUG):
        r = login(client, "secret-guess-123")
        login(client)
    assert "secret-guess-123" not in caplog.text and PASSWORD not in caplog.text
    assert "secret-guess-123" not in r.text and PASSWORD not in r.text


def test_compare_is_on_bytes(monkeypatch):
    reload_settings(monkeypatch, ADMIN_PASSWORD="pässwörd-é")
    assert admin_service.password_matches("pässwörd-é") and not admin_service.password_matches("passwörd-é")


# --- startup ----------------------------------------------------------------

def test_default_password_refused_with_cookie_secure(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with pytest.raises(ValidationError) as e:
        Settings(_env_file=None)
    assert "ADMIN_PASSWORD" in str(e.value)
    assert DEFAULT_ADMIN_PASSWORD not in str(e.value)
    monkeypatch.setenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_custom_password_accepted_with_cookie_secure(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("ADMIN_PASSWORD", "un-vrai-secret-long")
    assert not Settings(_env_file=None).admin_password_is_default
    assert "un-vrai-secret-long" not in repr(Settings(_env_file=None))


def test_empty_password_refused(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_default_password_warns_at_startup(database_url, caplog):
    from app.main import create_app

    with caplog.at_level(logging.WARNING, logger="app.admin"):
        create_app()
    assert "ADMIN_PASSWORD" in caplog.text and PASSWORD not in caplog.text


def test_no_warning_with_custom_password(database_url, monkeypatch, caplog):
    from app.main import create_app

    reload_settings(monkeypatch, ADMIN_PASSWORD="un-vrai-secret-long")
    with caplog.at_level(logging.WARNING, logger="app.admin"):
        create_app()
    assert "ADMIN_PASSWORD" not in caplog.text

from unittest.mock import patch

from sqlalchemy.exc import OperationalError


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_db_down(client):
    with patch("sqlalchemy.orm.Session.execute", side_effect=OperationalError("x", {}, Exception())):
        r = client.get("/api/health")
    assert r.status_code == 503
    assert "detail" in r.json()


def test_cors_allowed_origin(client, monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://front.test")
    from fastapi.testclient import TestClient

    from app.main import create_app
    from config.settings import get_settings

    get_settings.cache_clear()
    try:
        c = TestClient(create_app())
        r = c.get("/api/health", headers={"Origin": "http://front.test"})
        assert r.headers["access-control-allow-origin"] == "http://front.test"
        r = c.get("/api/health", headers={"Origin": "http://evil.test"})
        assert "access-control-allow-origin" not in r.headers
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

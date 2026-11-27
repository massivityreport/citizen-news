"""Tests run against a real PostgreSQL: a throwaway database is created from DATABASE_URL's server,
migrated with Alembic, and dropped at the end of the session."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DB = "citizen_news_test"


@pytest.fixture(scope="session", autouse=True)
def database_url():
    base = make_url(os.environ["DATABASE_URL"])
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    url = base.set(database=TEST_DB).render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url

    from app.db import get_engine
    from config.settings import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    yield url
    get_engine().dispose()
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def session(database_url):
    from sqlalchemy.orm import Session

    from app.db import get_engine

    with Session(get_engine()) as s:
        yield s
        s.rollback()
        # Clean tables between tests (CASCADE handles FKs).
        s.execute(text("TRUNCATE feedback, selections, edition_topics, editions, articles, topics, accounts, login_tokens, sessions, admin_sessions, media_sources, deleted_sources RESTART IDENTITY CASCADE"))
        s.commit()


@pytest.fixture
def client(database_url, session):  # `session` truncates tables after each test
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    from app.services.ratelimit import get_rate_limiter

    get_rate_limiter.cache_clear()
    yield
    get_rate_limiter.cache_clear()


@pytest.fixture
def mails():
    from tests.helpers import RecordingMailer

    return RecordingMailer()


@pytest.fixture
def api(client, mails):
    from app.services.mailer import get_mailer

    client.app.dependency_overrides[get_mailer] = lambda: mails
    return client


@pytest.fixture
def topics(session):
    from app.models import Topic

    ts = [Topic(title=f"Sujet {i}") for i in range(3)]
    session.add_all(ts)
    session.commit()
    return [t.id for t in ts]


@pytest.fixture
def logged(client, session):
    """A client with a valid session cookie; `client.account_id` is the account."""
    from app.deps import SESSION_COOKIE
    from app.models import Account
    from app.services import auth

    account = Account(email="a@example.org")
    session.add(account)
    session.commit()
    token, _ = auth.create_session(session, account)
    client.cookies.set(SESSION_COOKIE, token)
    client.account_id = account.id
    return client


@pytest.fixture(autouse=True)
def _no_real_dns(monkeypatch):
    """No test resolves a name for real: every name is a public address unless a test injects its own resolver."""
    from app.services import safe_fetch

    monkeypatch.setattr(safe_fetch, "system_resolver", lambda host, port: ["93.184.216.34"])

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
        s.execute(text("TRUNCATE votes, articles, topics, accounts, login_tokens, sessions, media_sources RESTART IDENTITY CASCADE"))
        s.commit()


@pytest.fixture
def client(database_url, session):  # `session` truncates tables after each test
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _no_stale_front_cache():
    from app.routers.topics import clear_front_cache

    clear_front_cache()
    yield
    clear_front_cache()

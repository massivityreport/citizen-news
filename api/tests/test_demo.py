import pytest
from sqlalchemy import func, select

from app import cli
from app.models import Article, MediaSource, Topic
from config.settings import get_settings


@pytest.fixture
def demo_on(monkeypatch):
    monkeypatch.setenv("DEMO_SEED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def test_seed_demo_is_refused_by_default(session, monkeypatch):
    monkeypatch.delenv("DEMO_SEED", raising=False)
    get_settings.cache_clear()
    assert cli.main(["seed-demo"]) == 2
    assert session.scalar(select(func.count()).select_from(Topic)) == 0


def test_seed_demo_is_refused_in_production(session, monkeypatch, demo_on):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("ADMIN_PASSWORD", "un-vrai-secret-long")  # otherwise the settings themselves are refused
    get_settings.cache_clear()
    assert cli.main(["seed-demo"]) == 2
    assert session.scalar(select(func.count()).select_from(Topic)) == 0


def test_seed_demo_creates_demo_topics_with_articles(session, demo_on):
    assert cli.main(["seed-demo"]) == 0
    session.expire_all()
    topics = list(session.scalars(select(Topic)))
    assert topics and all(t.title.startswith("[Démo]") for t in topics)
    assert session.scalar(select(func.count()).select_from(Article)) >= len(topics)
    assert all(m.feed_url.startswith("https://demo.invalid/") for m in session.scalars(select(MediaSource)))
    # a mix of widely, little and single-medium covered topics
    covers = set(session.execute(select(func.count(func.distinct(Article.source_id))).group_by(Article.topic_id)).scalars())
    assert covers == {1, 2, 3}


def test_seed_demo_can_be_repeated_without_duplicates(session, demo_on):
    assert cli.main(["seed-demo"]) == 0
    counts = [session.scalar(select(func.count()).select_from(m)) for m in (Topic, Article, MediaSource)]
    assert cli.main(["seed-demo"]) == 0
    session.expire_all()
    assert counts == [session.scalar(select(func.count()).select_from(m)) for m in (Topic, Article, MediaSource)]

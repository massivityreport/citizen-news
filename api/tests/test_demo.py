from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app import cli
from app.models import Account, Article, Edition, EditionTopic, MediaSource, Selection, Topic
from app.services.aggregation import aggregate
from app.services.demo import seed_demo
from app.services.edition_calendar import edition_state
from app.services.edition_close import close_due_edition
from app.services.pool import eligible_pool
from config.settings import get_settings

NOW = datetime(2026, 11, 27, 16, 30, tzinfo=UTC)  # 17:30 Paris: today's edition is closed and pending
MODELS = (Topic, Article, MediaSource, Account, Selection, Edition, EditionTopic)


def counts(session):
    session.expire_all()
    return [session.scalar(select(func.count()).select_from(m)) for m in MODELS]


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


def test_seed_demo_cli_reports_and_creates_the_whole_scene(session, demo_on):
    assert cli.main(["seed-demo"]) == 0
    topics, articles, media, accounts, selections, editions, edition_topics = counts(session)
    assert topics >= 15 and articles >= topics and accounts == 12 and editions == 3 and edition_topics > 0
    assert all(t.title.startswith("[Démo]") for t in session.scalars(select(Topic)))
    assert all(m.feed_url.startswith("https://demo.invalid/") and not m.active for m in session.scalars(select(MediaSource)))
    assert all(a.email.endswith("@example.invalid") for a in session.scalars(select(Account)))


def test_demo_pool_has_varied_coverage_images_and_recent_articles(session):
    seed_demo(session, now=NOW)
    pool = eligible_pool(session, NOW)
    assert len(pool) == session.scalar(select(func.count()).select_from(Topic))  # every demo topic is eligible
    sources = {e.source_count for e in pool}
    assert min(sources) >= 2 and {2, 3} <= sources and max(sources) > get_settings().radar_max_sources
    assert len([e for e in pool if e.source_count <= get_settings().radar_max_sources]) >= 3  # "Sous les radars"
    images = list(session.scalars(select(Article.image_url).where(Article.image_url.is_not(None))))
    assert images and all(i.startswith("https://") for i in images)
    oldest = session.scalar(select(func.min(Article.published_at)))
    assert (NOW - oldest).total_seconds() < 24 * 3600


def test_demo_unes_give_ties_and_a_cut_at_ten(session):
    report = seed_demo(session, now=NOW)
    assert report.edition_date == edition_state(session, NOW).edition_date
    per_account = list(session.execute(select(func.count()).select_from(Selection).group_by(Selection.account_id)).scalars())
    assert len(per_account) == 12 and max(per_account) <= 10
    result = aggregate(session, report.edition_date, NOW)
    assert result.participants == 12 and len(result.ranking) > 10
    assert any(t.crosses_cut for t in result.ties)  # a tie group straddles ranks 10 and 11
    assert {"source_count", "updated_at"} <= {t.broken_by for t in result.ties}
    approved = {t.topic_id for t in result.ranking}
    assert any(e.topic_id not in approved for e in eligible_pool(session, NOW))  # topics nobody picked


def test_demo_past_editions_are_published_and_coherent(session):
    seed_demo(session, now=NOW)
    editions = list(session.scalars(select(Edition).order_by(Edition.edition_date.desc())))
    assert [e.edition_date.isoformat() for e in editions] == ["2026-11-26", "2026-11-25", "2026-11-24"]
    for e in editions:
        rows = list(session.scalars(select(EditionTopic).where(EditionTopic.edition_id == e.id).order_by(EditionTopic.rank)))
        assert [r.rank for r in rows] == list(range(1, len(rows) + 1)) and len(rows) >= 5
        assert all(r.approvals <= e.participants and r.sources for r in rows)
        assert [r.approvals for r in rows] == sorted((r.approvals for r in rows), reverse=True)


def test_closing_publishes_the_ranking_the_preview_shows(session):
    report = seed_demo(session, now=NOW)
    expected = [(t.rank, t.title, t.score) for t in aggregate(session, report.edition_date, NOW).topics]
    edition = close_due_edition(session, NOW)
    assert edition.edition_date == report.edition_date and edition.participants == 12
    rows = session.scalars(select(EditionTopic).where(EditionTopic.edition_id == edition.id).order_by(EditionTopic.rank))
    assert [(r.rank, r.title, r.approvals) for r in rows] == expected and len(expected) == 10


def test_seed_demo_can_be_repeated_without_duplicates(session, demo_on):
    assert cli.main(["seed-demo"]) == 0
    first = counts(session)
    assert cli.main(["seed-demo"]) == 0
    assert counts(session) == first


def test_seed_demo_keeps_real_data_and_reset_clears_editions(session):
    session.add_all([Topic(title="Vrai sujet"), Account(email="vrai@exemple.fr"), Edition(edition_date=datetime(2026, 11, 20).date(), participants=0)])
    session.commit()
    seed_demo(session, now=NOW)
    seed_demo(session, now=NOW)
    assert session.scalar(select(Topic).where(Topic.title == "Vrai sujet")) and session.scalar(select(Account).where(Account.email == "vrai@exemple.fr"))
    assert session.scalar(select(func.count()).select_from(Edition)) == 4
    seed_demo(session, now=NOW, reset=True)
    assert session.scalar(select(func.count()).select_from(Edition)) == 3  # the real one is gone, the demo ones are back
    assert session.scalar(select(Topic).where(Topic.title == "Vrai sujet"))


def test_close_edition_now_is_allowed_with_dry_run_only_unless_demo(session, monkeypatch, capsys):
    monkeypatch.delenv("DEMO_SEED", raising=False)
    get_settings.cache_clear()
    report = seed_demo(session, now=NOW)
    assert cli.main(["close-edition", "--dry-run", "--now", NOW.isoformat()]) == 0
    out = capsys.readouterr().out
    assert f"édition {report.edition_date}" in out and "--- coupure ---" in out
    assert cli.main(["close-edition", "--now", NOW.isoformat()]) == 2  # real closing at a fake time: refused
    assert session.scalar(select(func.count()).select_from(Edition)) == 3  # nothing published
    with pytest.raises(SystemExit):
        cli.main(["close-edition", "--dry-run", "--now", "2026-11-27T17:30:00"])  # no time zone
    with pytest.raises(SystemExit):
        cli.main(["close-edition", "--dry-run", "--now", "demain"])


def test_close_edition_now_publishes_in_development(session, demo_on):
    seed_demo(session, now=NOW)
    assert cli.main(["close-edition", "--now", NOW.isoformat()]) == 0
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Edition)) == 4

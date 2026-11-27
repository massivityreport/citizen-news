"""close_due_edition(): what is published, when, once, atomically."""

import threading
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.deps import clock
from app.models.entities import Edition, EditionTopic, Topic
from app.services import edition_close
from app.services.edition_close import close_due_edition
from tests.helpers import make_accounts, make_article, make_sources, make_topic, put_une

DAY = date(2026, 11, 27)
CLOSING = datetime(2026, 11, 27, 16, 0, tzinfo=UTC)  # 17:00 Paris, winter


@pytest.fixture
def media(session):
    return make_sources(session, "A", "B", "C")


def topic(session, media, title="T", n=2, hours_ago=1.0, now=CLOSING):
    return make_topic(session, title, media[:n], hours_ago=hours_ago, now=now)


def previous_edition(session, day=date(2026, 11, 26)):
    session.add(Edition(edition_date=day, participants=0))
    session.commit()


def editions(session):
    session.expire_all()
    return list(session.scalars(select(Edition).order_by(Edition.edition_date)))


def two_unes(session, media, day=DAY, now=CLOSING):
    a, b = topic(session, media, "A", now=now), topic(session, media, "B", now=now)
    x, y, z = make_accounts(session, 3)
    put_une(session, x, day, [a.id, b.id])
    put_une(session, y, day, [a.id])
    session.commit()
    return a, b


def test_publishes_the_ranking_frozen(session, media):
    a, b = two_unes(session, media)
    edition = close_due_edition(session, CLOSING)
    assert (edition.edition_date, edition.participants, edition.published_at) == (DAY, 2, CLOSING)
    rows = session.scalars(select(EditionTopic).where(EditionTopic.edition_id == edition.id).order_by(EditionTopic.rank)).all()
    assert [(r.rank, r.topic_id, r.approvals, r.proportion) for r in rows] == [(1, a.id, 2, 1.0), (2, b.id, 1, 0.5)]
    assert rows[0].title == "A" and rows[0].source_count == 2 and len(rows[0].sources) == 2


def test_nothing_before_the_closing_instant(session, media):
    two_unes(session, media)
    assert close_due_edition(session, CLOSING - timedelta(seconds=1)) is None
    assert editions(session) == []
    assert close_due_edition(session, CLOSING) is not None


def test_summer_time_closes_at_15_utc(session, media):
    day = date(2026, 7, 15)
    closing = datetime(2026, 7, 15, 15, 0, tzinfo=UTC)  # 17:00 Paris (UTC+2)
    two_unes(session, media, day=day, now=closing)
    assert close_due_edition(session, datetime(2026, 7, 15, 14, 59, tzinfo=UTC)) is None
    assert close_due_edition(session, closing).edition_date == day


def test_winter_time_does_not_close_at_15_utc(session, media):
    two_unes(session, media)
    assert close_due_edition(session, datetime(2026, 11, 27, 15, 0, tzinfo=UTC)) is None


def test_idempotent(session, media):
    two_unes(session, media)
    assert close_due_edition(session, CLOSING) is not None
    assert close_due_edition(session, CLOSING + timedelta(minutes=1)) is None
    assert len(editions(session)) == 1
    assert session.scalar(select(func.count()).select_from(EditionTopic)) == 2


def test_empty_edition_is_published(session, media):
    previous_edition(session)
    topic(session, media)
    session.commit()
    edition = close_due_edition(session, CLOSING)
    assert (edition.edition_date, edition.participants) == (DAY, 0)
    assert session.scalar(select(func.count()).select_from(EditionTopic)) == 0


def test_no_ghost_edition_at_first_launch(session, media):
    topic(session, media)
    session.commit()
    assert close_due_edition(session, CLOSING) is None and editions(session) == []


def test_unpublished_topics_out_of_the_pool_do_not_count(session, media):
    previous_edition(session)
    inside, single = topic(session, media, "in"), topic(session, media, "one", n=1)
    [acct] = make_accounts(session, 1)
    put_une(session, acct, DAY, [single.id, inside.id])
    session.commit()
    edition = close_due_edition(session, CLOSING)
    assert [r.topic_id for r in session.scalars(select(EditionTopic).where(EditionTopic.edition_id == edition.id))] == [inside.id]


def test_catch_up_after_midnight_publishes_the_due_day(session, media):
    two_unes(session, media)
    late = datetime(2026, 11, 28, 0, 30, tzinfo=UTC)  # 01:30 Paris on the 28th, worker was down
    edition = close_due_edition(session, late)
    assert edition.edition_date == DAY and edition.published_at == late


def test_catch_up_after_several_days_publishes_only_the_latest_due(session, media):
    previous_edition(session, date(2026, 11, 20))
    now = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)  # 21, 22, 23 are due (24 not yet)
    t = topic(session, media, now=now)
    for day in (date(2026, 11, 21), date(2026, 11, 23)):
        [acct] = make_accounts(session, 1)
        put_une(session, acct, day, [t.id])
    session.commit()
    edition = close_due_edition(session, now)
    assert edition.edition_date == date(2026, 11, 23) and edition.participants == 1
    assert [e.edition_date for e in editions(session)] == [date(2026, 11, 20), date(2026, 11, 23)]
    assert close_due_edition(session, now) is None


def test_frozen_after_the_topic_changes_or_disappears(session, media):
    a, _ = two_unes(session, media)
    close_due_edition(session, CLOSING)
    a.title = "Autre titre"
    a.summary = "Autre résumé"
    make_article(session, media[2], "late", "Nouvel article", hours_ago=0.1, now=CLOSING, topic_id=a.id)
    session.commit()
    row = session.scalar(select(EditionTopic).where(EditionTopic.rank == 1))
    assert (row.title, row.summary, row.source_count, row.article_count) == ("A", "Résumé de A", 2, 2)
    session.execute(delete(Topic).where(Topic.id == a.id))
    session.commit()
    session.expire_all()
    row = session.scalar(select(EditionTopic).where(EditionTopic.rank == 1))
    assert row.topic_id is None and row.title == "A"


def test_two_simultaneous_closings_make_one_edition(session, media):
    two_unes(session, media)
    barrier = threading.Barrier(2)
    results = []

    def worker():
        with Session(get_engine()) as s:
            barrier.wait()
            results.append(close_due_edition(s, CLOSING))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert sorted(r is None for r in results) == [False, True]
    assert len(editions(session)) == 1
    assert session.scalar(select(func.count()).select_from(EditionTopic)) == 2


def test_unique_constraint_is_the_safety_net(session, media, monkeypatch):
    """Even if the lock and the pending check let a second closing through, the database refuses a duplicate."""
    two_unes(session, media)
    close_due_edition(session, CLOSING)
    monkeypatch.setattr(edition_close, "pending_editions", lambda s, n: [DAY])
    assert close_due_edition(session, CLOSING) is None
    assert len(editions(session)) == 1


def test_failure_midway_publishes_nothing(session, media, monkeypatch):
    two_unes(session, media)

    def boom(*a):
        raise RuntimeError("panne")

    monkeypatch.setattr(edition_close, "_insert_topics", boom)
    with pytest.raises(RuntimeError):
        close_due_edition(session, CLOSING)
    assert editions(session) == []
    assert session.scalar(select(func.count()).select_from(EditionTopic)) == 0
    monkeypatch.undo()
    assert close_due_edition(session, CLOSING) is not None  # the next tick publishes
    assert len(editions(session)) == 1


def test_writes_refused_after_closing_even_before_the_worker_publishes_then_the_next_day_starts_empty(session, media, logged):
    a, _ = two_unes(session, media)
    logged.app.dependency_overrides[clock] = lambda: CLOSING
    r = logged.put(f"/api/me/une/topics/{a.id}")
    assert r.status_code == 409 and "clôture" in r.json()["detail"]
    close_due_edition(session, CLOSING)
    body = logged.get("/api/me/une").json()
    assert (body["edition_date"], body["open"], body["topic_ids"]) == ("2026-11-28", True, [])
    assert logged.put(f"/api/me/une/topics/{a.id}").status_code == 200

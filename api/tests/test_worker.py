"""The worker's closing tick and the close-edition command."""

import threading
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import cli
from app.models.entities import Edition
from tests.helpers import make_accounts, make_sources, make_topic, put_une

DAY = date(2026, 11, 27)
CLOSING = datetime(2026, 11, 27, 16, 0, tzinfo=UTC)


@pytest.fixture
def unes(session):
    media = make_sources(session, "A", "B")
    a, b = (make_topic(session, t, media, now=CLOSING) for t in ("Alpha", "Beta"))
    x, y = make_accounts(session, 2)
    put_une(session, x, DAY, [a.id, b.id])
    put_une(session, y, DAY, [a.id])
    session.commit()


def count(session):
    session.expire_all()
    return session.scalar(select(func.count()).select_from(Edition))


def fixed_clock(monkeypatch, instant):
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant

    monkeypatch.setattr(cli, "datetime", Fixed)


def test_run_close_publishes_once(session, unes):
    assert cli.run_close(now=CLOSING) == 0
    assert cli.run_close(now=CLOSING + timedelta(minutes=1)) == 0
    assert count(session) == 1


def test_run_close_does_nothing_before_the_closing(session, unes):
    cli.run_close(now=CLOSING - timedelta(minutes=1))
    assert count(session) == 0


def test_first_tick_after_a_long_stop_publishes_the_latest_due(session, unes):
    session.add(Edition(edition_date=date(2026, 11, 20), participants=0))
    session.commit()
    cli.run_close(now=CLOSING + timedelta(hours=2))  # worker was down since the 20th: 21..27 are due
    session.expire_all()
    assert [e.edition_date for e in session.scalars(select(Edition).order_by(Edition.edition_date))] == [date(2026, 11, 20), DAY]


def test_close_loop_survives_errors_stops_on_event_and_ticks_at_once(monkeypatch):
    stop = threading.Event()
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        stop.set()

    monkeypatch.setattr(cli, "run_close", flaky)
    assert cli.run_close_loop(stop, interval_seconds=0.001) == 0
    assert len(calls) == 2


def test_close_loop_does_not_tick_when_already_stopped(monkeypatch):
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(cli, "run_close", lambda: pytest.fail("tick after stop"))
    assert cli.run_close_loop(stop) == 0


def test_worker_runs_ingestion_and_closing_separately_and_stops_both(monkeypatch):
    stop = threading.Event()
    seen = set()
    closing = threading.Event()

    def close():
        seen.add(threading.current_thread().name)
        closing.set()

    def refresh():
        closing.wait(10)  # the ingestion loop waits for the closing tick: they run side by side
        seen.add(threading.current_thread().name)
        stop.set()

    monkeypatch.setattr(cli, "run_close", close)
    monkeypatch.setattr(cli, "run_refresh", refresh)
    assert cli.run_worker(0.0001, stop) == 0
    assert "close-tick" in seen and len(seen) == 2  # the closing ticked in its own thread
    assert not any(t.name == "close-tick" and t.is_alive() for t in threading.enumerate())


def test_a_slow_ingestion_does_not_delay_the_closing(monkeypatch):
    stop = threading.Event()
    ticked = threading.Event()
    monkeypatch.setattr(cli, "run_close", lambda: ticked.set())
    monkeypatch.setattr(cli, "run_refresh", lambda: (ticked.wait(10), stop.set()))
    cli.run_worker(60, stop)
    assert ticked.is_set()


def test_close_edition_command_publishes(session, unes, monkeypatch):
    fixed_clock(monkeypatch, CLOSING)
    assert cli.main(["close-edition"]) == 0
    assert count(session) == 1


def test_dry_run_prints_the_ranking_and_publishes_nothing(session, unes, monkeypatch, capsys):
    fixed_clock(monkeypatch, CLOSING)
    assert cli.main(["close-edition", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "2 participants" in out and out.index("Alpha") < out.index("Beta") and "2 approbations" in out
    assert count(session) == 0


def test_dry_run_before_the_closing_shows_the_edition_in_progress(session, unes, monkeypatch, capsys):
    fixed_clock(monkeypatch, CLOSING - timedelta(hours=1))
    cli.main(["close-edition", "--dry-run"])
    assert "pas encore due" in capsys.readouterr().out and count(session) == 0

import threading

import pytest
from sqlalchemy import func, select

from app import cli
from app.models.entities import Article
from tests.test_ingest import ALPHA, BETA, make_client


def test_refresh_ingests_then_clusters(session, monkeypatch):
    from app.services import ingest as ingest_module

    monkeypatch.setattr(ingest_module, "load_feeds", lambda: [ALPHA, BETA])
    monkeypatch.setattr(ingest_module, "make_client", make_client)
    assert cli.main(["refresh"]) == 0
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Article)) == 4


def test_loop_stops_on_event_and_survives_errors(monkeypatch):
    stop = threading.Event()
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        stop.set()

    monkeypatch.setattr(cli, "run_refresh", flaky)
    assert cli.run_loop(0.0001, stop) == 0
    assert len(calls) == 2


def test_run_rejects_non_positive_interval():
    with pytest.raises(SystemExit):
        cli.main(["run", "--interval-minutes", "0"])


def test_invalid_interval_env_gives_clear_error(monkeypatch):
    monkeypatch.setenv("INGEST_INTERVAL_MINUTES", "abc")
    with pytest.raises(SystemExit, match="INGEST_INTERVAL_MINUTES"):
        cli.main(["run"])


def test_halve_command_applies_the_halving(session):
    from app.models import Topic
    from tests.helpers import add_votes

    good, weak = Topic(title="Bon sujet"), Topic(title="Sujet faible")
    session.add_all([good, weak])
    session.flush()
    add_votes(session, good, more=18, not_priority=2)
    add_votes(session, weak, more=2, not_priority=18)
    session.commit()
    assert cli.main(["halve"]) == 0
    session.expire_all()
    assert (good.state, good.wave) == ("active", 1)
    assert (weak.state, weak.wave) == ("reserve", 0)
    assert cli.main(["halve"]) == 0  # idempotent
    session.expire_all()
    assert (good.state, weak.state) == ("active", "reserve")


def test_refresh_also_halves(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_ingest", lambda: calls.append("ingest") or 0)
    monkeypatch.setattr(cli, "run_cluster", lambda: calls.append("cluster") or 0)
    monkeypatch.setattr(cli, "run_halve", lambda: calls.append("halve") or 0)
    assert cli.run_refresh() == 0
    assert calls == ["ingest", "cluster", "halve"]


def test_refresh_keeps_the_clustering_exit_code_and_still_halves(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_ingest", lambda: calls.append("ingest") or 0)
    monkeypatch.setattr(cli, "run_cluster", lambda: calls.append("cluster") or 3)
    monkeypatch.setattr(cli, "run_halve", lambda: calls.append("halve") or 0)
    assert cli.run_refresh() == 3
    assert calls == ["ingest", "cluster", "halve"]


def test_refresh_runs_every_step_when_ingest_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_ingest", lambda: calls.append("ingest") or 2)
    monkeypatch.setattr(cli, "run_cluster", lambda: calls.append("cluster") or 0)
    monkeypatch.setattr(cli, "run_halve", lambda: calls.append("halve") or 0)
    assert cli.run_refresh() == 2
    assert calls == ["ingest", "cluster", "halve"]

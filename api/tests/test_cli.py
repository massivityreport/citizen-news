import threading

import pytest
from sqlalchemy import func, select

from app import cli
from app.models.entities import Article
from tests.test_ingest import ALPHA, BETA, make_client


def test_refresh_ingests_then_clusters(session, monkeypatch):
    from app.services import ingest as ingest_module

    monkeypatch.setattr(ingest_module, "load_feeds", lambda: [ALPHA, BETA])
    real = ingest_module.fetch_public
    monkeypatch.setattr(ingest_module, "fetch_public", lambda url, **kw: real(url, **{**kw, "client": make_client()}))
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


def test_halve_command_is_gone():
    with pytest.raises(SystemExit):
        cli.main(["halve"])


def test_refresh_runs_ingest_then_cluster_only(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_ingest", lambda: calls.append("ingest") or 0)
    monkeypatch.setattr(cli, "run_cluster", lambda: calls.append("cluster") or 0)
    assert cli.run_refresh() == 0
    assert calls == ["ingest", "cluster"]


def test_refresh_keeps_the_clustering_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "run_ingest", lambda: 0)
    monkeypatch.setattr(cli, "run_cluster", lambda: 3)
    assert cli.run_refresh() == 3


def test_refresh_runs_every_step_when_ingest_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_ingest", lambda: calls.append("ingest") or 2)
    monkeypatch.setattr(cli, "run_cluster", lambda: calls.append("cluster") or 0)
    assert cli.run_refresh() == 2
    assert calls == ["ingest", "cluster"]

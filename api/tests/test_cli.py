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

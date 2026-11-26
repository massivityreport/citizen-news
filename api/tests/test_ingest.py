from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.models.entities import Article, MediaSource
from app.services.ingest import ingest, parse_feed
from app.services.text import clean_html, truncate
from config.feeds import FeedConfig

FIXTURES = Path(__file__).parent / "fixtures"
ALPHA = FeedConfig(name="Alpha", feed_url="https://alpha.example/rss")
BETA = FeedConfig(name="Beta", feed_url="https://beta.example/rss")
BROKEN = FeedConfig(name="Cassé", feed_url="https://broken.example/rss")
DOWN = FeedConfig(name="Panne", feed_url="https://down.example/rss")


def make_client(routes: dict[str, bytes | int] | None = None) -> httpx.Client:
    routes = routes or {
        ALPHA.feed_url: (FIXTURES / "feed_alpha.xml").read_bytes(),
        BETA.feed_url: (FIXTURES / "feed_beta.xml").read_bytes(),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = routes.get(str(request.url), 404)
        if isinstance(body, int):
            return httpx.Response(body)
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_clean_html_and_truncate():
    assert clean_html("<p>Un &amp; deux<br>trois</p><style>a{}</style>  fin&nbsp;!") == "Un & deux trois fin !"
    assert clean_html(None) == ""
    assert truncate("court", 280) == "court"
    out = truncate("mot " * 100, 50)
    assert len(out) <= 50 and out.endswith("mot…")


def test_parse_feed_cleans_skips_and_dedups():
    articles = parse_feed((FIXTURES / "feed_alpha.xml").read_bytes())
    assert [a.url for a in articles] == ["https://alpha.example/retraites-1", "https://alpha.example/canicule"]
    first = articles[0]
    assert first.summary == "Le gouvernement & les syndicats se retrouvent lundi pour discuter des retraites."
    assert first.published_at == datetime(2026, 11, 25, 10, tzinfo=UTC)


def test_parse_feed_caps_future_dates():
    now = datetime(2026, 11, 25, 10, 30, tzinfo=UTC)
    articles = parse_feed((FIXTURES / "feed_alpha.xml").read_bytes(), now=now)
    assert articles[1].published_at == now


def test_parse_garbage_raises():
    with pytest.raises(ValueError):
        parse_feed(b"<html><body>pas un flux")


def test_ingest_stores_articles_and_syncs_sources(session):
    report = ingest(session, [ALPHA, BETA], client=make_client())
    assert report.new_articles == 4 and not report.failed
    assert session.scalar(select(func.count()).select_from(Article)) == 4
    assert {s.name for s in session.scalars(select(MediaSource))} == {"Alpha", "Beta"}


def test_ingest_is_idempotent(session):
    ingest(session, [ALPHA, BETA], client=make_client())
    report = ingest(session, [ALPHA, BETA], client=make_client())
    assert report.new_articles == 0
    assert session.scalar(select(func.count()).select_from(Article)) == 4
    assert session.scalar(select(func.count()).select_from(MediaSource)) == 2


def test_renamed_source_is_updated_not_duplicated(session):
    ingest(session, [ALPHA], client=make_client())
    ingest(session, [FeedConfig(name="Alpha Info", feed_url=ALPHA.feed_url)], client=make_client())
    assert [s.name for s in session.scalars(select(MediaSource))] == ["Alpha Info"]


def test_failing_feeds_do_not_stop_the_others(session):
    routes = {
        BROKEN.feed_url: b"<html>not a feed",
        BETA.feed_url: (FIXTURES / "feed_beta.xml").read_bytes(),
    }  # DOWN is a 404
    report = ingest(session, [BROKEN, DOWN, BETA], client=make_client(routes))
    assert {f.name for f in report.failed} == {"Cassé", "Panne"}
    assert report.new_articles == 2
    assert session.scalar(select(func.count()).select_from(Article)) == 2

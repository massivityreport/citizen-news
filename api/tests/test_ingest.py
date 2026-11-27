from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.models.entities import Article, MediaSource
from app.services.images import validate_image_url
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


def test_renamed_in_yaml_does_not_rename_the_source(session):
    # the database is the reference: feeds.yaml never overwrites a name an admin may have chosen
    ingest(session, [ALPHA], client=make_client())
    ingest(session, [FeedConfig(name="Alpha Info", feed_url=ALPHA.feed_url)], client=make_client())
    assert [s.name for s in session.scalars(select(MediaSource))] == ["Alpha"]


def test_failing_feeds_do_not_stop_the_others(session):
    routes = {
        BROKEN.feed_url: b"<html>not a feed",
        BETA.feed_url: (FIXTURES / "feed_beta.xml").read_bytes(),
    }  # DOWN is a 404
    report = ingest(session, [BROKEN, DOWN, BETA], client=make_client(routes))
    assert {f.name for f in report.failed} == {"Cassé", "Panne"}
    assert report.new_articles == 2
    assert session.scalar(select(func.count()).select_from(Article)) == 2


def test_conflict_refreshes_text_only_when_changed_and_keeps_first_date(session):
    from sqlalchemy import text

    ingest(session, [ALPHA], client=make_client())
    first = session.scalars(select(Article).where(Article.url == "https://alpha.example/canicule")).one()
    session.execute(text("UPDATE articles SET title='ancien titre', published_at='2020-01-01' WHERE id=:i"), {"i": first.id})
    session.commit()
    report = ingest(session, [ALPHA], client=make_client())
    session.expire_all()
    refreshed = session.get(Article, first.id)
    assert report.new_articles == 0
    assert refreshed.title.startswith("Canicule")  # changed text refreshed
    assert refreshed.published_at.year == 2020  # date untouched by the conflict update


# --- images (hotlink only: only a validated URL is kept) ---

IMAGES = FeedConfig(name="Images", feed_url="https://img.example/rss")


def _images_by_url() -> dict[str, str | None]:
    articles = parse_feed((FIXTURES / "feed_images.xml").read_bytes())
    return {a.url.rsplit("/a/", 1)[1]: a.image_url for a in articles}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://cdn.example/a.jpg", "https://cdn.example/a.jpg"),
        ("HTTPS://CDN.example/a.jpg", "https://cdn.example/a.jpg"),  # scheme and host lowercased
        ("https://café.example/a.jpg", "https://xn--caf-dma.example/a.jpg"),  # IDN stored as punycode
        ("https://cdn.example:8443/a.jpg?w=1#x", "https://cdn.example:8443/a.jpg?w=1#x"),
        ("https://93.184.216.34/a.jpg", "https://93.184.216.34/a.jpg"),
        ("https://[2606:4700::1111]/a.jpg", "https://[2606:4700::1111]/a.jpg"),
        ("  https://cdn.example/a.jpg  ", "https://cdn.example/a.jpg"),
        ("http://cdn.example/a.jpg", None),
        ("data:image/png;base64,AAAA", None),
        ("javascript:alert(1)", None),
        ("ftp://cdn.example/a.jpg", None),
        ("https://", None),
        ("https:///a.jpg", None),
        ("https://user:pw@cdn.example/a.jpg", None),
        ("https://user@cdn.example/a.jpg", None),
        ("https://cdn.example/a b.jpg", None),
        ("https://cdn.example/a\n.jpg", None),
        ("https://cdn.example/a\x00.jpg", None),
        ("https://cdn.example:notaport/a.jpg", None),
        ("https://cdn.example:99999/a.jpg", None),
        ("https://cdn.example:0/a.jpg", None),
        ("https://evil.com\\.good.com/x.jpg", None),  # a browser reads \ as /
        ("https://cdn.example\\a.jpg", None),
        ("\\\\evil.com/x.jpg", None),
        ("/\\evil.com/x.jpg", None),
        ("https://cdn.example/a\"b.jpg", None),
        ("https://cdn.example/a'b.jpg", None),
        ("https://cdn.example/a<b>.jpg", None),
        ("https://.", None),
        ("https://cdn..example/a.jpg", None),
        ("https://cdn.example./a.jpg", None),
        ("https://cdn_x.example/a.jpg", None),
        ("https://localhost/a.jpg", None),
        ("https://LOCALHOST:8443/a.jpg", None),
        ("https://img.localhost/a.jpg", None),
        ("https://127.0.0.1/a.jpg", None),
        ("https://10.0.0.5/a.jpg", None),
        ("https://172.16.0.1/a.jpg", None),
        ("https://192.168.1.1/a.jpg", None),
        ("https://169.254.169.254/a.jpg", None),
        ("https://100.64.0.1/a.jpg", None),
        ("https://0.0.0.0/a.jpg", None),
        ("https://240.0.0.1/a.jpg", None),
        ("https://2130706433/a.jpg", None),  # decimal 127.0.0.1
        ("https://0x7f.1/a.jpg", None),
        ("https://127.1/a.jpg", None),
        ("https://[::1]/a.jpg", None),
        ("https://[::]/a.jpg", None),
        ("https://[fe80::1]/a.jpg", None),
        ("https://[fc00::1]/a.jpg", None),
        ("https://[::ffff:127.0.0.1]/a.jpg", None),
        ("", None),
        (None, None),
        (42, None),
    ],
)
def test_validate_image_url(raw, expected):
    assert validate_image_url(raw, "https://news.example/article") == expected


def test_validate_image_url_length_bound():
    prefix = "https://cdn.example/"
    assert validate_image_url(prefix + "a" * (500 - len(prefix))) is not None
    assert validate_image_url(prefix + "a" * (501 - len(prefix))) is None


def test_validate_image_url_resolves_relative_against_article():
    base = "https://news.example/section/article"
    assert validate_image_url("/media/x.jpg", base) == "https://news.example/media/x.jpg"
    assert validate_image_url("x.jpg", base) == "https://news.example/section/x.jpg"
    assert validate_image_url("//cdn.example/x.jpg", base) == "https://cdn.example/x.jpg"
    # an http article gives an http image: rejected
    assert validate_image_url("/media/x.jpg", "http://news.example/a") is None
    assert validate_image_url("/media/x.jpg") is None


def test_parse_feed_image_sources_and_priority():
    images = _images_by_url()
    assert images["media-content"] == "https://cdn.example/mc.jpg"
    assert images["media-type"] == "https://cdn.example/typed.png"
    assert images["thumb"] == "https://cdn.example/thumb.jpg"
    assert images["enclosure"] == "https://cdn.example/enc.jpg"
    assert images["summary"] == "https://img.example/media/relative.jpg"
    assert images["content"] == "https://cdn.example/content.jpg"


def test_parse_feed_invalid_candidate_falls_back_to_next_then_none():
    images = _images_by_url()
    assert images["fallback"] == "https://cdn.example/fallback.jpg"
    assert images["invalid"] is None
    assert images["none"] is None


def test_parse_feed_without_images():
    assert {a.image_url for a in parse_feed((FIXTURES / "feed_alpha.xml").read_bytes())} == {None}


def test_ingest_stores_image_url(session):
    client = make_client({IMAGES.feed_url: (FIXTURES / "feed_images.xml").read_bytes()})
    ingest(session, [IMAGES], client)
    stored = dict(session.execute(select(Article.url, Article.image_url)).all())
    assert stored["https://img.example/a/media-content"] == "https://cdn.example/mc.jpg"
    assert stored["https://img.example/a/none"] is None


def test_ingest_backfills_image_of_existing_article_only(session):
    plain = b"""<rss version="2.0"><channel><title>x</title>
    <item><title>Article connu</title><link>https://img.example/a/known</link>
    <pubDate>Wed, 25 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    with_image = b"""<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>x</title>
    <item><title>Article connu</title><link>https://img.example/a/known</link>
    <pubDate>Wed, 25 Nov 2026 23:00:00 GMT</pubDate>
    <media:content url="https://cdn.example/new.jpg" medium="image"/></item></channel></rss>"""
    other = with_image.replace(b"new.jpg", b"other.jpg")
    ingest(session, [IMAGES], make_client({IMAGES.feed_url: plain}))
    article = session.scalars(select(Article)).one()
    assert article.image_url is None
    session.execute(Article.__table__.update().values(topic_id=None))
    first_date, first_title = article.published_at, article.title
    session.commit()

    report = ingest(session, [IMAGES], make_client({IMAGES.feed_url: with_image}))
    session.expire_all()
    article = session.scalars(select(Article)).one()
    assert report.new_articles == 0
    assert article.image_url == "https://cdn.example/new.jpg"
    assert (article.published_at, article.title) == (first_date, first_title)

    ingest(session, [IMAGES], make_client({IMAGES.feed_url: other}))  # an existing image is kept
    session.expire_all()
    assert session.scalars(select(Article.image_url)).one() == "https://cdn.example/new.jpg"
    ingest(session, [IMAGES], make_client({IMAGES.feed_url: plain}))  # a feed that dropped it keeps it
    session.expire_all()
    assert session.scalars(select(Article.image_url)).one() == "https://cdn.example/new.jpg"


def test_ingest_backfill_leaves_topic_assignment_untouched(session):
    from app.models.entities import Topic

    source = MediaSource(name="Images", feed_url=IMAGES.feed_url)
    topic = Topic(title="Sujet existant")
    session.add_all([source, topic])
    session.flush()
    published = datetime(2026, 11, 25, 10, tzinfo=UTC)
    session.add(Article(source_id=source.id, url="https://img.example/a/known", title="Article connu",
                        published_at=published, topic_id=topic.id))
    session.commit()
    topic_id, updated_at = topic.id, topic.updated_at
    feed = b"""<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>x</title>
    <item><title>Article connu</title><link>https://img.example/a/known</link>
    <pubDate>Wed, 25 Nov 2026 23:00:00 GMT</pubDate>
    <media:content url="https://cdn.example/new.jpg" medium="image"/></item></channel></rss>"""
    ingest(session, [IMAGES], make_client({IMAGES.feed_url: feed}))
    session.expire_all()
    article = session.scalars(select(Article)).one()
    assert article.image_url == "https://cdn.example/new.jpg"
    assert article.topic_id == topic_id and article.published_at == published
    assert session.get(Topic, topic_id).updated_at == updated_at


# --- the database is the reference (feeds.yaml only seeds it) ---

def _fetched_urls(client_log: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        client_log.append(str(request.url))
        return httpx.Response(200, content=(FIXTURES / "feed_alpha.xml").read_bytes())

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_sync_sources_only_adds_missing_sources(session):
    from app.services.ingest import sync_sources

    assert sync_sources(session, [ALPHA, BETA]) == 2
    assert sync_sources(session, [ALPHA, BETA]) == 0
    assert sync_sources(session, [ALPHA, BETA, BROKEN]) == 1
    assert session.scalar(select(func.count()).select_from(MediaSource)) == 3


def test_sync_sources_never_reactivates(session):
    from app.services.ingest import sync_sources

    sync_sources(session, [ALPHA])
    session.execute(MediaSource.__table__.update().values(active=False))
    sync_sources(session, [ALPHA])
    assert session.scalars(select(MediaSource.active)).all() == [False]


def test_sync_sources_does_not_recreate_a_deleted_source(session):
    from app.models.entities import DeletedSource
    from app.services.ingest import sync_sources

    session.add(DeletedSource(feed_url=ALPHA.feed_url))
    session.flush()
    assert sync_sources(session, [ALPHA, BETA]) == 1
    assert session.scalars(select(MediaSource.feed_url)).all() == [BETA.feed_url]


def test_new_sources_are_active_by_default(session):
    ingest(session, [ALPHA], client=make_client())
    assert session.scalars(select(MediaSource.active)).all() == [True]


def test_ingest_skips_inactive_sources_but_keeps_their_articles(session):
    ingest(session, [ALPHA, BETA], client=make_client())
    beta = session.scalars(select(MediaSource).where(MediaSource.feed_url == BETA.feed_url)).one()
    beta.active = False
    session.commit()
    fetched: list[str] = []
    report = ingest(session, [ALPHA, BETA], client=_fetched_urls(fetched))
    assert fetched == [ALPHA.feed_url]
    assert [f.name for f in report.feeds] == ["Alpha"]
    assert session.scalar(select(func.count()).select_from(Article).where(Article.source_id == beta.id)) == 2


def test_ingest_fetches_sources_added_in_the_database(session):
    session.add(MediaSource(name="Ajoutée", feed_url="https://added.example/rss"))
    session.commit()
    fetched: list[str] = []
    ingest(session, [], client=_fetched_urls(fetched))
    assert fetched == ["https://added.example/rss"]

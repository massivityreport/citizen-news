"""RSS ingestion: fetch feeds, parse entries, upsert articles (deduplicated by URL)."""

import logging
from calendar import timegm
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import feedparser
import httpx
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.entities import Article, MediaSource
from app.services.images import extract_image_url
from app.services.text import clean_html, truncate
from config.feeds import FeedConfig, load_feeds

log = logging.getLogger(__name__)

USER_AGENT = "CitizenNewsBot/0.1 (RSS reader)"
FETCH_TIMEOUT_SECONDS = 15.0
MAX_FEED_BYTES = 5_000_000
MAX_TITLE_CHARS = 500
MAX_SUMMARY_CHARS = 1000


@dataclass(frozen=True)
class ParsedArticle:
    url: str
    title: str
    summary: str
    published_at: datetime | None
    image_url: str | None = None


@dataclass
class FeedResult:
    name: str
    feed_url: str
    fetched: int = 0
    error: str | None = None


@dataclass
class IngestReport:
    feeds: list[FeedResult] = field(default_factory=list)
    new_articles: int = 0

    @property
    def failed(self) -> list[FeedResult]:
        return [f for f in self.feeds if f.error]


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
    )


def sync_sources(session: Session, feeds: Sequence[FeedConfig]) -> dict[str, int]:
    """Make media_sources match the config (by feed_url); returns {feed_url: source id}.
    Sources removed from the config are kept, so their articles stay attached."""
    for feed in feeds:
        session.execute(
            insert(MediaSource)
            .values(name=feed.name, feed_url=feed.feed_url)
            .on_conflict_do_update(index_elements=["feed_url"], set_={"name": feed.name})
        )
    session.flush()
    rows = session.execute(select(MediaSource.feed_url, MediaSource.id)).all()
    return {url: id_ for url, id_ in rows}


def parse_feed(content: bytes, now: datetime | None = None) -> list[ParsedArticle]:
    """Parse a feed document (no network). Entries without http(s) link or title are skipped;
    dates in the future are capped to `now`."""
    now = now or datetime.now(UTC)
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"flux illisible : {parsed.bozo_exception}")
    articles: dict[str, ParsedArticle] = {}
    for entry in parsed.entries:
        url = (entry.get("link") or "").strip()
        parts = urlsplit(url)
        title = clean_html(entry.get("title"))[:MAX_TITLE_CHARS]
        if parts.scheme not in ("http", "https") or not parts.hostname or not title:
            continue
        summary = truncate(clean_html(entry.get("summary") or entry.get("description")), MAX_SUMMARY_CHARS)
        stamp = entry.get("published_parsed") or entry.get("updated_parsed")
        published = datetime.fromtimestamp(timegm(stamp), UTC) if stamp else None
        if published and published > now:
            published = now  # a feed date in the future (clock skew) would hide the article from the window
        articles.setdefault(url, ParsedArticle(url, title, summary, published, extract_image_url(entry, url)))
    return list(articles.values())


def fetch_feed(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    if len(response.content) > MAX_FEED_BYTES:
        raise ValueError("flux trop volumineux")
    return response.content


def upsert_articles(session: Session, source_id: int, articles: Sequence[ParsedArticle]) -> int:
    """Insert articles by URL; an existing URL has its title/summary refreshed only if they changed.
    An existing article with no image gets the feed's image if it now has a valid one (UPDATE of
    image_url alone: no topic_id, no published_at).

    published_at is deliberately left out of the conflict update: the first date seen is kept, so an
    article never moves in the clustering window and the topic assignment stays stable.
    Returns the number of newly inserted articles."""
    new = 0
    for a in articles:
        insert_stmt = insert(Article).values(
            source_id=source_id, url=a.url, title=a.title, summary=a.summary,
            published_at=a.published_at, image_url=a.image_url,
        )
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["url"],
            set_={
                "title": insert_stmt.excluded.title,
                "summary": insert_stmt.excluded.summary,
                # backfill only: an image already stored is never replaced
                "image_url": func.coalesce(Article.image_url, insert_stmt.excluded.image_url),
            },
            where=(Article.title.is_distinct_from(insert_stmt.excluded.title))
            | (Article.summary.is_distinct_from(insert_stmt.excluded.summary))
            | (Article.image_url.is_(None) & insert_stmt.excluded.image_url.is_not(None)),
            # xmax = 0 is how PostgreSQL tells an inserted row from one updated by ON CONFLICT: there is
            # no portable alternative in a single statement. An unchanged conflict returns no row.
        ).returning(literal_column("(xmax = 0)").label("inserted"))
        new += bool(session.execute(stmt).scalar_one_or_none())
    return new


def ingest(
    session: Session,
    feeds: Sequence[FeedConfig] | None = None,
    client: httpx.Client | None = None,
) -> IngestReport:
    """Fetch every configured feed. A failing feed is reported and never stops the others."""
    feeds = load_feeds() if feeds is None else feeds
    source_ids = sync_sources(session, feeds)
    session.commit()
    own_client = client is None
    client = client or make_client()
    report = IngestReport()
    try:
        for feed in feeds:
            result = FeedResult(feed.name, feed.feed_url)
            report.feeds.append(result)
            try:
                articles = parse_feed(fetch_feed(client, feed.feed_url))
                report.new_articles += upsert_articles(session, source_ids[feed.feed_url], articles)
                session.commit()
                result.fetched = len(articles)
            except Exception as exc:  # one broken feed must not stop the others
                session.rollback()
                result.error = f"{type(exc).__name__}: {exc}"[:300]
                log.warning("feed %s failed: %s", feed.name, result.error)
    finally:
        if own_client:
            client.close()
    return report

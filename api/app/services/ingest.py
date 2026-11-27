"""RSS ingestion: fetch feeds, parse entries, upsert articles (deduplicated by URL)."""

import logging
from calendar import timegm
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import feedparser
import httpx
from sqlalchemy import func, literal, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.entities import Article, DeletedSource, MediaSource
from app.services.feed_url import FeedUrlError, normalize_feed_url
from app.services.images import extract_image_url
from app.services.safe_fetch import FetchError, Resolver, fetch_public
from app.services.text import clean_html, truncate
from config.feeds import FeedConfig, load_feeds

log = logging.getLogger(__name__)

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


SOURCES_LOCK_KEY = 0x636E5F73  # arbitrary constant shared by sync_sources and delete_source


def lock_sources(session: Session) -> None:
    """Transaction-level advisory lock: seeding and permanent deletion of sources never interleave, so a
    deletion committed while the seeding runs cannot be undone by it. Released at commit/rollback."""
    session.execute(select(func.pg_advisory_xact_lock(SOURCES_LOCK_KEY)))


def sync_sources(session: Session, feeds: Sequence[FeedConfig]) -> int:
    """Seed media_sources from the config. The DATABASE is the reference: feeds.yaml only adds the feeds
    that are missing (by normalized feed_url). It never renames a source, never re-activates a deactivated
    one and never re-creates one an admin deleted for good (deleted_sources). Returns the number added.

    Each insert is one INSERT ... SELECT ... WHERE NOT EXISTS (deleted_sources), taken under the advisory
    lock that delete_source also takes: no deletion can slip in between the check and the insert."""
    lock_sources(session)
    added = 0
    for feed in feeds:
        try:
            url = normalize_feed_url(feed.feed_url)
        except FeedUrlError as exc:
            log.warning("feed %s ignored: %s", feed.name, exc)
            continue
        wanted = select(literal(feed.name), literal(url)).where(
            ~select(DeletedSource.id).where(DeletedSource.feed_url == url).exists()
        )
        result = session.execute(
            insert(MediaSource)
            .from_select(["name", "feed_url"], wanted)
            .on_conflict_do_nothing(index_elements=["feed_url"])
            .returning(MediaSource.id)
        )
        added += result.first() is not None
    session.flush()
    return added


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
    resolver: Resolver | None = None,
) -> IngestReport:
    """Seed missing sources from feeds.yaml, then fetch every ACTIVE source of the database (deactivated
    sources are not fetched; their articles stay). A failing feed is reported and never stops the others."""
    feeds = load_feeds() if feeds is None else feeds
    sync_sources(session, feeds)
    sources = session.execute(
        select(MediaSource.id, MediaSource.name, MediaSource.feed_url).where(MediaSource.active).order_by(MediaSource.id)
    ).all()
    session.commit()
    report = IngestReport()
    for source_id, name, feed_url in sources:
        result = FeedResult(name, feed_url)
        report.feeds.append(result)
        try:
            articles = parse_feed(fetch_public(feed_url, client=client, resolver=resolver, max_bytes=MAX_FEED_BYTES))
            report.new_articles += upsert_articles(session, source_id, articles)
            session.commit()
            result.fetched = len(articles)
        except Exception as exc:  # one broken feed must not stop the others
            session.rollback()
            detail = exc.reason if isinstance(exc, FetchError) else str(exc)
            result.error = f"{type(exc).__name__}: {detail}"[:300]
            log.warning("feed %s failed: %s", name, result.error)
    return report

"""Read side of topics: eligibility rules and TopicCard building (no N+1: 2 queries per request)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Article, MediaSource, Topic
from app.schemas import SourceOut, TopicCard
from config.clustering import ClusteringParams


def eligible_topics(params: ClusteringParams, now: datetime | None = None):
    """Topics shown to citizens: active within the window and reported by enough DISTINCT media
    (several articles from one medium never count as several sources)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=params.window_hours)
    distinct_sources = (
        select(Article.topic_id)
        .group_by(Article.topic_id)
        .having(func.count(func.distinct(Article.source_id)) >= params.min_sources_for_front)
    )
    return select(Topic).where(Topic.updated_at >= cutoff, Topic.id.in_(distinct_sources))


def build_cards(session: Session, topics: list[Topic]) -> list[TopicCard]:
    """TopicCards for `topics` (order kept). `sources` holds one entry per medium: its latest article.
    `article_count` / `source_count`: all the topic's articles / distinct media. `image_url` is the image of the topic's most recent article that has one, else None."""
    if not topics:
        return []
    rows = session.execute(
        select(
            Article.topic_id, MediaSource.name, Article.url, Article.title, Article.published_at, Article.fetched_at,
            Article.id, Article.image_url, Article.source_id,
        )
        .join(MediaSource, MediaSource.id == Article.source_id)
        .where(Article.topic_id.in_([t.id for t in topics]))
    ).all()
    latest: dict[tuple[int, str], tuple] = {}
    images: dict[int, tuple] = {}
    articles: dict[int, int] = {t.id: 0 for t in topics}
    media: dict[int, set[int]] = {t.id: set() for t in topics}
    for topic_id, name, url, title, published_at, fetched_at, article_id, image_url, source_id in rows:
        articles[topic_id] += 1
        media[topic_id].add(source_id)
        if image_url:  # most recent article (published_at desc, nulls last, then id desc) that has one
            rank = (published_at or datetime.min.replace(tzinfo=UTC), article_id)
            if topic_id not in images or rank > images[topic_id][0]:
                images[topic_id] = (rank, image_url)
        day = published_at or fetched_at
        key = (topic_id, name)
        if key not in latest or (day, url) > (latest[key][0], latest[key][1]):
            latest[key] = (day, url, title, published_at)
    by_topic: dict[int, list[SourceOut]] = {t.id: [] for t in topics}
    for (topic_id, name), (day, url, title, published_at) in sorted(
        latest.items(), key=lambda kv: (kv[1][0], kv[0][1]), reverse=True
    ):
        by_topic[topic_id].append(SourceOut(name=name, url=url, title=title, published_at=published_at))
    return [
        TopicCard(
            id=t.id,
            title=t.title,
            summary=t.summary,
            sources=by_topic[t.id],
            article_count=articles[t.id],
            source_count=len(media[t.id]),
            first_seen_at=t.first_seen_at,
            updated_at=t.updated_at,
            image_url=images[t.id][1] if t.id in images else None,
        )
        for t in topics
    ]

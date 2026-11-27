"""Back office: paginated list of articles with their source and topic.

Two SQL statements whatever the page size: the page (articles JOIN media_sources LEFT JOIN topics,
LIMIT/OFFSET) and a COUNT on `articles` alone (every filter is on an articles column). The ORDER BY comes
from a closed table (SORTS), never from the input; the article id breaks ties, so the order is total.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, UTC
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Article, MediaSource, Topic
from app.schemas import AdminArticleOut, AdminArticlePage, AdminSourceRef, AdminTopicRef

SortKey = Literal["date", "source", "topic"]
Order = Literal["asc", "desc"]

# Closed list of sortable expressions. Ungrouped articles / undated articles come last in both directions.
SORTS = {
    "date": Article.published_at,
    "source": func.lower(MediaSource.name),
    "topic": func.lower(Topic.title),
}


@dataclass(frozen=True)
class ArticleFilters:
    topic_id: int | None = None
    source_id: int | None = None
    date_from: date | None = None  # inclusive, 00:00 UTC
    date_to: date | None = None  # inclusive: the whole day, up to the next 00:00 UTC (exclusive)
    ungrouped: bool = False


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def list_articles(
    session: Session, filters: ArticleFilters, sort: SortKey, order: Order, page: int, page_size: int
) -> AdminArticlePage:
    where = []
    if filters.topic_id is not None:
        where.append(Article.topic_id == filters.topic_id)
    if filters.ungrouped:
        where.append(Article.topic_id.is_(None))
    if filters.source_id is not None:
        where.append(Article.source_id == filters.source_id)
    if filters.date_from is not None:
        where.append(Article.published_at >= _day_start(filters.date_from))
    if filters.date_to is not None:
        where.append(Article.published_at < _day_start(filters.date_to + timedelta(days=1)))

    total = session.scalar(select(func.count()).select_from(Article).where(*where)) or 0
    key = SORTS[sort]
    direction = (lambda c: c.asc()) if order == "asc" else (lambda c: c.desc())
    rows = session.execute(
        select(
            Article.id, Article.title, Article.url, Article.published_at, Article.fetched_at,
            MediaSource.id, MediaSource.name, MediaSource.active, Topic.id, Topic.title,
        )
        .join(MediaSource, MediaSource.id == Article.source_id)
        .outerjoin(Topic, Topic.id == Article.topic_id)
        .where(*where)
        .order_by(direction(key).nulls_last(), direction(Article.id))
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    items = [
        AdminArticleOut(
            id=a_id, title=title, url=url, published_at=published_at, fetched_at=fetched_at,
            source=AdminSourceRef(id=s_id, name=s_name, active=s_active),
            topic=None if t_id is None else AdminTopicRef(id=t_id, title=t_title),
            grouped=t_id is not None,
        )
        for a_id, title, url, published_at, fetched_at, s_id, s_name, s_active, t_id, t_title in rows
    ]
    return AdminArticlePage(items=items, total=total, page=page, page_size=page_size)

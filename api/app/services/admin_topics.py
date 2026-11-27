"""Back office: topics with their aggregates and one topic's detail (articles included).

Read only, nothing personal. V1 votes and halving states are gone; approvals (selections of the current
edition) come with the V2 admin task.
"""

from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import Date, cast, func, literal_column, select
from sqlalchemy.orm import Session

from app.models.entities import Article, MediaSource, Topic
from app.schemas import AdminSourceRef, AdminTopicArticle, AdminTopicDetail, AdminTopicPage, AdminTopicRow

TopicSort = Literal["title", "articles", "updated"]
Order = Literal["asc", "desc"]
MAX_TOPIC_ARTICLES = 200


def list_topics(session: Session, sort: TopicSort, order: Order, page: int, page_size: int) -> AdminTopicPage:
    articles = (
        select(
            Article.topic_id.label("topic_id"),
            func.count().label("articles"),
            func.count(func.distinct(Article.source_id)).label("sources"),
        )
        .group_by(Article.topic_id)
        .subquery()
    )
    n_articles = func.coalesce(articles.c.articles, 0)
    n_sources = func.coalesce(articles.c.sources, 0)
    image = (
        select(Article.image_url)
        .where(Article.topic_id == Topic.id, Article.image_url.is_not(None))
        .order_by(Article.published_at.desc().nulls_last(), Article.id.desc())  # same choice as the citizen cards
        .limit(1)
        .scalar_subquery()
    )
    sorts = {"title": func.lower(Topic.title), "articles": n_articles, "updated": Topic.updated_at}
    total = session.scalar(select(func.count()).select_from(Topic)) or 0
    direction = (lambda c: c.asc()) if order == "asc" else (lambda c: c.desc())
    rows = session.execute(
        select(Topic.id, Topic.title, Topic.updated_at, n_articles, n_sources, image)
        .outerjoin(articles, articles.c.topic_id == Topic.id)
        .order_by(direction(sorts[sort]).nulls_last(), direction(Topic.id))
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    items = [
        AdminTopicRow(id=i, title=t, updated_at=u, article_count=a, source_count=so, image_url=img)
        for i, t, u, a, so, img in rows
    ]
    return AdminTopicPage(items=items, total=total, page=page, page_size=page_size)


def day_bucket(column):
    """The UTC calendar day of a timestamp column, as a SQL date (the convention of every daily curve)."""
    return cast(func.date_trunc(literal_column("'day'"), func.timezone(literal_column("'UTC'"), column)), Date)


def utc_midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=UTC)


def topic_detail(session: Session, topic_id: int) -> AdminTopicDetail | None:
    topic = session.get(Topic, topic_id)
    if topic is None:
        return None
    n_articles, n_sources = session.execute(
        select(func.count(), func.count(func.distinct(Article.source_id))).where(Article.topic_id == topic_id)
    ).one()
    article_rows = session.execute(
        select(Article.id, Article.title, Article.url, Article.published_at, MediaSource.id, MediaSource.name, MediaSource.active)
        .join(MediaSource, MediaSource.id == Article.source_id)
        .where(Article.topic_id == topic_id)
        .order_by(Article.published_at.desc().nulls_last(), Article.id.desc())
        .limit(MAX_TOPIC_ARTICLES)
    ).all()
    return AdminTopicDetail(
        id=topic.id, title=topic.title, summary=topic.summary,
        first_seen_at=topic.first_seen_at, updated_at=topic.updated_at,
        article_count=n_articles, source_count=n_sources,
        articles=[
            AdminTopicArticle(id=i, title=t, url=u, published_at=p, source=AdminSourceRef(id=s, name=n, active=a))
            for i, t, u, p, s, n, a in article_rows
        ],
        articles_truncated=n_articles > MAX_TOPIC_ARTICLES,
    )

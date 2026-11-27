"""Back office: topics with their aggregates and one topic's detail (articles included).

Read only, nothing personal. `approvals` = accounts that have the topic in their une of the edition in
progress (`edition_state`); the detail adds the history over the published editions. All computed by SQL aggregates.
"""

from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import Date, cast, func, literal_column, select
from sqlalchemy.orm import Session

from app.models.entities import Article, Edition, EditionTopic, MediaSource, Selection, Topic
from app.schemas import (
    AdminSourceRef, AdminTopicArticle, AdminTopicDetail, AdminTopicHistory, AdminTopicPage, AdminTopicRow,
)
from app.services.edition_calendar import edition_state

TopicSort = Literal["approvals", "title", "articles", "updated"]
HISTORY_EDITIONS = 30
Order = Literal["asc", "desc"]
MAX_TOPIC_ARTICLES = 200


def _approvals(session: Session, now: datetime | None):
    """Subquery: approvals of the edition in progress per topic."""
    day = edition_state(session, now).edition_date
    return (
        select(Selection.topic_id.label("topic_id"), func.count(func.distinct(Selection.account_id)).label("approvals"))
        .where(Selection.edition_date == day)
        .group_by(Selection.topic_id)
        .subquery()
    )


def list_topics(
    session: Session, sort: TopicSort, order: Order, page: int, page_size: int, now: datetime | None = None
) -> AdminTopicPage:
    current = _approvals(session, now)
    n_approvals = func.coalesce(current.c.approvals, 0)
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
    sorts = {"title": func.lower(Topic.title), "articles": n_articles, "updated": Topic.updated_at, "approvals": n_approvals}
    total = session.scalar(select(func.count()).select_from(Topic)) or 0
    direction = (lambda c: c.asc()) if order == "asc" else (lambda c: c.desc())
    rows = session.execute(
        select(Topic.id, Topic.title, Topic.updated_at, n_articles, n_sources, n_approvals, image)
        .outerjoin(articles, articles.c.topic_id == Topic.id)
        .outerjoin(current, current.c.topic_id == Topic.id)
        .order_by(direction(sorts[sort]).nulls_last(), direction(Topic.id))
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    items = [
        AdminTopicRow(id=i, title=t, updated_at=u, article_count=a, source_count=so, approvals=ap, image_url=img)
        for i, t, u, a, so, ap, img in rows
    ]
    return AdminTopicPage(items=items, total=total, page=page, page_size=page_size)


def day_bucket(column):
    """The UTC calendar day of a timestamp column, as a SQL date (the convention of every daily curve)."""
    return cast(func.date_trunc(literal_column("'day'"), func.timezone(literal_column("'UTC'"), column)), Date)


def utc_midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=UTC)


def topic_detail(session: Session, topic_id: int, now: datetime | None = None) -> AdminTopicDetail | None:
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
    current = session.scalar(
        select(func.count(func.distinct(Selection.account_id))).where(
            Selection.topic_id == topic_id, Selection.edition_date == edition_state(session, now).edition_date
        )
    )
    return AdminTopicDetail(
        id=topic.id, title=topic.title, summary=topic.summary,
        first_seen_at=topic.first_seen_at, updated_at=topic.updated_at,
        article_count=n_articles, source_count=n_sources,
        articles=[
            AdminTopicArticle(id=i, title=t, url=u, published_at=p, source=AdminSourceRef(id=s, name=n, active=a))
            for i, t, u, p, s, n, a in article_rows
        ],
        articles_truncated=n_articles > MAX_TOPIC_ARTICLES,
        approvals=current or 0,
        history=_history(session, topic_id),
    )


def _history(session: Session, topic_id: int) -> list[AdminTopicHistory]:
    """Published editions where the topic is in the une (frozen figures) or had approvals without making it
    (counted from the selections, over the frozen participants). Last 30 editions, most recent first."""
    chosen = (
        select(Selection.edition_date.label("day"), func.count(func.distinct(Selection.account_id)).label("n"))
        .where(Selection.topic_id == topic_id)
        .group_by(Selection.edition_date)
        .subquery()
    )
    approvals = func.coalesce(EditionTopic.approvals, chosen.c.n)
    rows = session.execute(
        select(
            Edition.edition_date,
            EditionTopic.rank,
            approvals,
            func.coalesce(EditionTopic.proportion, chosen.c.n * 1.0 / func.nullif(Edition.participants, 0), 0.0),
        )
        .select_from(Edition)
        .outerjoin(EditionTopic, (EditionTopic.edition_id == Edition.id) & (EditionTopic.topic_id == topic_id))
        .outerjoin(chosen, chosen.c.day == Edition.edition_date)
        .where(approvals.is_not(None))
        .order_by(Edition.edition_date.desc())
        .limit(HISTORY_EDITIONS)
    ).all()
    return [AdminTopicHistory(edition_date=d, rank=r, approvals=a, proportion=round(float(p), 3)) for d, r, a, p in rows]

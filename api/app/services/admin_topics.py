"""Back office: topics with their aggregates, one topic's status and votes.

Nothing personal leaves here: a vote is (date, choice, account id). Business rules are not re-implemented:
the support score and level come from support.py (the halving's Wilson bound), the reason shown on the front
page from front.py (`front_entry`, the function that builds the front page itself).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import Date, case, cast, func, literal_column, select
from sqlalchemy.orm import Session

from app.models.entities import Article, MediaSource, Topic, Vote
from app.schemas import (
    AdminFrontOut, AdminSourceRef, AdminSupportOut, AdminTopicArticle, AdminTopicDetail, AdminTopicPage,
    AdminTopicRow, AdminVoteDay, AdminVoteOut, AdminVotePage, AdminVoteSummary,
)
from app.services.front import front_entry
from app.services.support import VoteStats, level_for, load_vote_stats
from config.clustering import ClusteringParams
from config.front import FrontParams

TopicSort = Literal["title", "state", "votes", "articles", "state_changed"]
Order = Literal["asc", "desc"]
DAILY_WINDOW_DAYS = 30
MAX_TOPIC_ARTICLES = 200
# Life cycle order, for sorting by state.
STATE_ORDER = case({"new": 0, "active": 1, "emerged": 2, "reserve": 3}, value=Topic.state)


def list_topics(
    session: Session, state: str | None, sort: TopicSort, order: Order, page: int, page_size: int
) -> AdminTopicPage:
    articles = (
        select(
            Article.topic_id.label("topic_id"),
            func.count().label("articles"),
            func.count(func.distinct(Article.source_id)).label("sources"),
        )
        .group_by(Article.topic_id)
        .subquery()
    )
    votes = select(Vote.topic_id.label("topic_id"), func.count().label("n")).group_by(Vote.topic_id).subquery()
    n_articles = func.coalesce(articles.c.articles, 0)
    n_sources = func.coalesce(articles.c.sources, 0)
    n_votes = func.coalesce(votes.c.n, 0)
    image = (
        select(Article.image_url)
        .where(Article.topic_id == Topic.id, Article.image_url.is_not(None))
        .order_by(Article.published_at.desc().nulls_last(), Article.id.desc())  # same choice as the citizen cards
        .limit(1)
        .scalar_subquery()
    )
    sorts = {
        "title": func.lower(Topic.title),
        "state": STATE_ORDER,
        "votes": n_votes,
        "articles": n_articles,
        "state_changed": Topic.state_changed_at,
    }
    where = [] if state is None else [Topic.state == state]
    total = session.scalar(select(func.count()).select_from(Topic).where(*where)) or 0
    direction = (lambda c: c.asc()) if order == "asc" else (lambda c: c.desc())
    rows = session.execute(
        select(Topic.id, Topic.title, Topic.state, Topic.wave, Topic.state_changed_at, n_articles, n_sources, n_votes, image)
        .outerjoin(articles, articles.c.topic_id == Topic.id)
        .outerjoin(votes, votes.c.topic_id == Topic.id)
        .where(*where)
        .order_by(direction(sorts[sort]).nulls_last(), direction(Topic.id))
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    items = [
        AdminTopicRow(
            id=i, title=t, state=s, wave=w, state_changed_at=c, article_count=a, source_count=so, vote_count=v, image_url=img
        )
        for i, t, s, w, c, a, so, v, img in rows
    ]
    return AdminTopicPage(items=items, total=total, page=page, page_size=page_size)


def day_bucket(column):
    """The UTC calendar day of a timestamp column, as a SQL date (the convention of every daily curve)."""
    return cast(func.date_trunc(literal_column("'day'"), func.timezone(literal_column("'UTC'"), column)), Date)


def utc_midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=UTC)


def _daily(session: Session, topic_id: int, first: datetime | None, now: datetime) -> list[AdminVoteDay]:
    """Votes per UTC day, the last 30 days (today included) or since the first vote if that is shorter.
    Aggregated in SQL; days without a vote are filled with zeros here."""
    if first is None:
        return []
    today = now.astimezone(UTC).date()
    start = max(first.astimezone(UTC).date(), today - timedelta(days=DAILY_WINDOW_DAYS - 1))
    day = day_bucket(Vote.created_at)
    rows = session.execute(
        select(
            day.label("day"),
            func.count().filter(Vote.choice == "more"),
            func.count().filter(Vote.choice == "not_priority"),
            func.count().filter(Vote.choice == "unknown"),
        )
        .where(
            Vote.topic_id == topic_id,
            Vote.created_at >= utc_midnight(start),
            Vote.created_at < utc_midnight(today + timedelta(days=1)),
        )
        .group_by(day)
    )
    found = {d: (m, n, u) for d, m, n, u in rows}
    out = []
    d: date = start
    while d <= today:
        m, n, u = found.get(d, (0, 0, 0))
        out.append(AdminVoteDay(date=d.isoformat(), more=m, not_priority=n, unknown=u, total=m + n + u))
        d += timedelta(days=1)
    return out


def topic_detail(
    session: Session, topic_id: int, clustering: ClusteringParams, cfg: FrontParams, now: datetime | None = None
) -> AdminTopicDetail | None:
    now = now or datetime.now(UTC)
    topic = session.get(Topic, topic_id)
    if topic is None:
        return None
    n_articles, n_sources = session.execute(
        select(func.count(), func.count(func.distinct(Article.source_id))).where(Article.topic_id == topic_id)
    ).one()
    stats = load_vote_stats(session, [topic_id], cfg, now).get(topic_id, VoteStats())
    voters, first_vote = session.execute(
        select(func.count(func.distinct(Vote.account_id)), func.min(Vote.created_at)).where(Vote.topic_id == topic_id)
    ).one()
    # The front page only knows topics that have articles (it joins on them): none, never on the front.
    entry = front_entry(topic, n_sources, stats, clustering, cfg, now) if n_articles else None
    on_front = entry is not None
    article_rows = session.execute(
        select(Article.id, Article.title, Article.url, Article.published_at, MediaSource.id, MediaSource.name, MediaSource.active)
        .join(MediaSource, MediaSource.id == Article.source_id)
        .where(Article.topic_id == topic_id)
        .order_by(Article.published_at.desc().nulls_last(), Article.id.desc())
        .limit(MAX_TOPIC_ARTICLES)
    ).all()
    return AdminTopicDetail(
        id=topic.id, title=topic.title, summary=topic.summary, state=topic.state, wave=topic.wave,
        first_seen_at=topic.first_seen_at, updated_at=topic.updated_at,
        state_changed_at=topic.state_changed_at, evaluated_at=topic.evaluated_at,
        article_count=n_articles, source_count=n_sources,
        support=AdminSupportOut(score=stats.score, level=level_for(stats, cfg), votes_count=stats.total),
        front=AdminFrontOut(on_front=on_front, reason=entry.reason if on_front else None),
        votes=AdminVoteSummary(
            more=stats.more, not_priority=stats.not_priority, unknown=stats.unknown, total=stats.total,
            voters=voters, first_vote_at=first_vote, daily=_daily(session, topic_id, first_vote, now),
        ),
        articles=[
            AdminTopicArticle(id=i, title=t, url=u, published_at=p, source=AdminSourceRef(id=s, name=n, active=a))
            for i, t, u, p, s, n, a in article_rows
        ],
        articles_truncated=n_articles > MAX_TOPIC_ARTICLES,
    )


def topic_votes(session: Session, topic_id: int, page: int, page_size: int) -> AdminVotePage | None:
    if session.get(Topic, topic_id) is None:
        return None
    total = session.scalar(select(func.count()).select_from(Vote).where(Vote.topic_id == topic_id)) or 0
    rows = session.execute(
        select(Vote.created_at, Vote.choice, Vote.account_id)  # the account NUMBER only, never the account row
        .where(Vote.topic_id == topic_id)
        .order_by(Vote.created_at.desc(), Vote.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return AdminVotePage(
        items=[AdminVoteOut(date=d, choice=c, account_id=a) for d, c, a in rows],
        total=total, page=page, page_size=page_size,
    )

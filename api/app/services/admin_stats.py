"""Back office: home page statistics (aggregated counts only, nothing personal).

Everything is computed by the database: five aggregate queries whatever the volume, never a table loaded in
memory. Days are UTC calendar days, same convention as a topic's vote curve (`admin_topics.day_bucket`).
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Article, Vote
from app.schemas import AdminStats, AdminStatsCounts, AdminStatsDay
from app.services.admin_topics import day_bucket, utc_midnight

SERIES_DAYS = 30
WINDOW = timedelta(hours=24)


def stats(session: Session, now: datetime | None = None) -> AdminStats:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    since = now - WINDOW  # sliding window [now - 24 h, now]
    today = now.date()
    first = today - timedelta(days=SERIES_DAYS - 1)
    lo, hi = utc_midnight(first), utc_midnight(today + timedelta(days=1))

    in_24h = Article.fetched_at.between(since, now)
    articles_total, articles_24h = session.execute(select(func.count(), func.count().filter(in_24h))).one()
    vote_24h = Vote.created_at.between(since, now)
    votes_total, votes_24h, voters_total, voters_24h = session.execute(
        select(
            func.count(),
            func.count().filter(vote_24h),
            func.count(func.distinct(Vote.account_id)),
            func.count(func.distinct(Vote.account_id)).filter(vote_24h),
        )
    ).one()

    # Ingestion day (fetched_at), then vote day; `voters` is distinct per day, not additive across days.
    a_day = day_bucket(Article.fetched_at)
    per_article = dict(
        session.execute(select(a_day, func.count()).where(Article.fetched_at >= lo, Article.fetched_at < hi).group_by(a_day)).all()
    )
    v_day = day_bucket(Vote.created_at)
    per_vote = {
        d: (n, v)
        for d, n, v in session.execute(
            select(v_day, func.count(), func.count(func.distinct(Vote.account_id)))
            .where(Vote.created_at >= lo, Vote.created_at < hi)
            .group_by(v_day)
        )
    }
    series = []
    d: date = first
    while d <= today:
        votes, voters = per_vote.get(d, (0, 0))
        series.append(AdminStatsDay(date=d.isoformat(), articles=per_article.get(d, 0), votes=votes, voters=voters))
        d += timedelta(days=1)
    return AdminStats(
        last_24h=AdminStatsCounts(articles=articles_24h, votes=votes_24h, voters=voters_24h),
        total=AdminStatsCounts(articles=articles_total, votes=votes_total, voters=voters_total),
        series=series,
    )

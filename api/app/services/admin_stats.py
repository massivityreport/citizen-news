"""Back office: home page statistics (aggregated counts only, nothing personal).

Everything is computed by the database: aggregate queries whatever the volume, never a table loaded in
memory. Days are UTC calendar days (`admin_topics.day_bucket`). Participants = distinct accounts with at least one selection (a non-empty une), selections = selection rows
(topics put in a une), both dated by `selections.created_at`.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Article, Selection
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

    # Ingestion day (fetched_at).
    a_day = day_bucket(Article.fetched_at)
    per_article = dict(
        session.execute(select(a_day, func.count()).where(Article.fetched_at >= lo, Article.fetched_at < hi).group_by(a_day)).all()
    )
    series = []
    d: date = first
    while d <= today:
        series.append(AdminStatsDay(date=d.isoformat(), articles=per_article.get(d, 0), participants=0, selections=0))
        d += timedelta(days=1)

    in_24h_sel = Selection.created_at.between(since, now)
    sel_total, sel_24h, people_total, people_24h = session.execute(
        select(
            func.count(),
            func.count().filter(in_24h_sel),
            func.count(func.distinct(Selection.account_id)),
            func.count(func.distinct(Selection.account_id)).filter(in_24h_sel),
        )
    ).one()
    s_day = day_bucket(Selection.created_at)
    per_selection = {
        d: (n, people)
        for d, n, people in session.execute(
            select(s_day, func.count(), func.count(func.distinct(Selection.account_id)))
            .where(Selection.created_at >= lo, Selection.created_at < hi)
            .group_by(s_day)
        )
    }
    series = [
        AdminStatsDay(date=p.date, articles=p.articles, selections=per_selection.get(date.fromisoformat(p.date), (0, 0))[0],
                      participants=per_selection.get(date.fromisoformat(p.date), (0, 0))[1])
        for p in series
    ]
    return AdminStats(
        last_24h=AdminStatsCounts(articles=articles_24h, participants=people_24h, selections=sel_24h),
        total=AdminStatsCounts(articles=articles_total, participants=people_total, selections=sel_total),
        series=series,
    )

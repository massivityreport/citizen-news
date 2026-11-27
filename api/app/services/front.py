"""The citizen front page: which topics, in which order, with which support and reason.

Candidates: topics active within the clustering window, not in `reserve`. A topic is kept when
  - it is covered by at least `min_sources_for_front` distinct media, OR its reason is `under_the_radar`;
  - it has at least `ranking.min_votes` votes OR it is recent (`ranking.recent_hours`);
  - it has a reason (see support.py).
Ranking: support_weight * score + freshness_weight * freshness, where freshness = 0.5 ** (age / half-life)
of the topic's latest article (`topics.updated_at`). Ties: most recent first. Three SQL statements
(topics with source counts, vote statistics, cards), whatever the number of topics.
Returns (the first `limit` topics, whether more ranked topics exist beyond them).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Article, Topic
from app.schemas import ReasonOut, SupportOut
from app.services.support import VoteStats, load_vote_stats, support_and_reason
from config.clustering import ClusteringParams
from config.front import FrontParams


@dataclass(frozen=True)
class FrontEntry:
    rank: float
    support: SupportOut
    reason: ReasonOut


def front_entry(
    topic: Topic, n_sources: int, stats: VoteStats, clustering: ClusteringParams, cfg: FrontParams, now: datetime
) -> FrontEntry | None:
    """The topic's place on the front page (rank, support, reason), or None when it is not kept.
    Single source of truth, used by the front page and by the back office ("is this topic on the front?")."""
    if topic.state == "reserve" or topic.updated_at < now - timedelta(hours=clustering.window_hours):
        return None  # (front_topics already filters these in SQL, to load fewer rows)
    found = support_and_reason(topic, stats, n_sources, cfg, now)
    if found is None:
        return None
    support, reason = found
    if n_sources < clustering.min_sources_for_front and reason.code != "under_the_radar":
        return None
    if stats.total < cfg.ranking.min_votes and topic.updated_at < now - timedelta(hours=cfg.ranking.recent_hours):
        return None
    age_hours = max((now - topic.updated_at).total_seconds() / 3600, 0.0)
    freshness = 0.5 ** (age_hours / cfg.ranking.freshness_half_life_hours)
    rank = cfg.ranking.support_weight * stats.score + cfg.ranking.freshness_weight * freshness
    return FrontEntry(rank, support, reason)


def front_topics(
    session: Session, limit: int, clustering: ClusteringParams, cfg: FrontParams, now: datetime | None = None
) -> tuple[list[tuple[Topic, SupportOut, ReasonOut]], bool]:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=clustering.window_hours)
    sources = (
        select(Article.topic_id.label("topic_id"), func.count(func.distinct(Article.source_id)).label("n"))
        .group_by(Article.topic_id)
        .subquery()
    )
    rows = session.execute(
        select(Topic, sources.c.n)
        .join(sources, sources.c.topic_id == Topic.id)
        .where(Topic.updated_at >= cutoff, Topic.state != "reserve")
    ).all()
    stats = load_vote_stats(session, (t.id for t, _ in rows), cfg, now)
    ranked = []
    for topic, n_sources in rows:
        entry = front_entry(topic, n_sources, stats.get(topic.id, VoteStats()), clustering, cfg, now)
        if entry is not None:
            ranked.append((entry.rank, topic, entry.support, entry.reason))
    ranked.sort(key=lambda r: (-r[0], -r[1].updated_at.timestamp(), -r[1].id))
    items = [(topic, support, reason) for _, topic, support, reason in ranked[:limit]]
    return items, len(ranked) > limit

"""The daily pool of topics and its tabs.

`eligible_pool` is THE eligibility rule: the pool endpoint, the une writes and the closing (aggregation) all
call it, never a copy of it. A topic is eligible when
- one of its articles is dated within the last POOL_WINDOW_HOURS (article date = published_at, else fetched_at;
  dates more than 1 h in the future are ignored), and
- its articles come from at least `min_sources_for_front` DISTINCT media (all its articles count, as in the cards).
One aggregated query whatever the number of topics.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Article, Topic
from config.clustering import load_clustering_params
from config.settings import get_settings

POOL_CAP = 300
FUTURE_TOLERANCE = timedelta(hours=1)
Tab = Literal["random", "recent", "radar"]


@dataclass(frozen=True)
class PoolEntry:
    topic_id: int
    updated_at: datetime
    article_count: int
    source_count: int


def eligible_pool(session: Session, now: datetime | None = None, topic_ids: list[int] | None = None) -> list[PoolEntry]:
    """Eligible topics at `now`, unordered. `topic_ids` restricts the check to those topics (same rule)."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=get_settings().pool_window_hours)
    day = func.coalesce(Article.published_at, Article.fetched_at)
    query = (
        select(Topic.id, Topic.updated_at, func.count(Article.id), func.count(func.distinct(Article.source_id)))
        .join(Article, Article.topic_id == Topic.id)
        .group_by(Topic.id)
        .having(
            # An article dated in the future (feed clock error) never keeps a topic in the pool: 1 h of tolerance.
            func.max(day).filter(day <= now + FUTURE_TOLERANCE) >= cutoff,
            func.count(func.distinct(Article.source_id)) >= load_clustering_params().min_sources_for_front,
        )
    )
    if topic_ids is not None:
        query = query.where(Topic.id.in_(topic_ids))
    return [PoolEntry(*row) for row in session.execute(query)]


def random_key(seed: str, topic_id: int) -> str:
    return hashlib.sha256(f"{seed}:{topic_id}".encode()).hexdigest()


def tab_entries(entries: list[PoolEntry], tab: Tab, seed: str | None) -> list[PoolEntry]:
    """Entries of the tab, in display order (not capped)."""
    if tab == "random":
        return sorted(entries, key=lambda e: random_key(seed or "", e.topic_id))
    if tab == "radar":
        entries = [e for e in entries if e.source_count <= get_settings().radar_max_sources]
    return sorted(entries, key=lambda e: (e.updated_at, e.topic_id), reverse=True)

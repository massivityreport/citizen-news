"""Support level and reason of a topic, from its votes (only accounts' votes count).

score = Wilson lower bound of the share of "more" among the opinions (see halving.py); `votes_count` is
the total of votes, "unknown" included. Thresholds: config/front.yaml.

Level: `high` / `medium` need both a minimum number of votes and a minimum score, otherwise `low`.

Reason (the first rule that matches wins; the v1 has no sensitivity groups, so no "alerte minoritaire"
nor "priorité transversale"):
  common_priority      many votes AND a high score (strong and broad)
  under_the_radar      covered by few media, but a high score
  strong_mobilisation  many "more" votes (with at least medium support)
  emerging             a surge of recent votes (with at least medium support), or a topic that reached
                       the `emerged` state recently
A topic matching none has no reason: the front page keeps it only if it is recent and has too few votes to
be judged yet, and then labels it `emerging` (documented default: a new topic worth watching).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Topic, Vote
from app.schemas import ReasonOut, SupportOut
from app.services.halving import wilson_lower_bound
from config.front import FrontParams

REASON_LABELS = {
    "common_priority": "Priorité commune",
    "strong_mobilisation": "Forte mobilisation",
    "under_the_radar": "Sous les radars",
    "emerging": "Sujet émergent",
}


@dataclass(frozen=True)
class VoteStats:
    more: int = 0
    not_priority: int = 0
    unknown: int = 0
    recent: int = 0  # votes created within `emerging.trend_hours`

    @property
    def total(self) -> int:
        return self.more + self.not_priority + self.unknown

    @property
    def score(self) -> float:
        return wilson_lower_bound(self.more, self.more + self.not_priority)


def load_vote_stats(session: Session, topic_ids: Iterable[int], cfg: FrontParams, now: datetime) -> dict[int, VoteStats]:
    ids = list(topic_ids)
    if not ids:
        return {}
    recent_cutoff = now - timedelta(hours=cfg.reasons.emerging.trend_hours)
    rows = session.execute(
        select(
            Vote.topic_id,
            func.count().filter(Vote.choice == "more"),
            func.count().filter(Vote.choice == "not_priority"),
            func.count().filter(Vote.choice == "unknown"),
            func.count().filter(Vote.created_at >= recent_cutoff),
        )
        .where(Vote.topic_id.in_(ids))
        .group_by(Vote.topic_id)
    )
    return {t: VoteStats(m, n, u, r) for t, m, n, u, r in rows}


def level_for(stats: VoteStats, cfg: FrontParams) -> str:
    s = cfg.support
    if stats.total >= s.high_min_votes and stats.score >= s.high_score:
        return "high"
    if stats.total >= s.medium_min_votes and stats.score >= s.medium_score:
        return "medium"
    return "low"


def reason_code(topic: Topic, stats: VoteStats, sources: int, cfg: FrontParams, now: datetime) -> str | None:
    """The reason code earned by the votes, or None."""
    r = cfg.reasons
    score, total = stats.score, stats.total
    if total >= r.common_priority.min_votes and score >= r.common_priority.min_score:
        return "common_priority"
    if sources <= r.under_the_radar.max_sources and total >= r.under_the_radar.min_votes and score >= r.under_the_radar.min_score:
        return "under_the_radar"
    if level_for(stats, cfg) == "low":
        return None  # the next two rules need at least medium support
    if stats.more >= r.strong_mobilisation.min_more_votes:
        return "strong_mobilisation"
    surging = stats.recent >= r.emerging.trend_min_votes and stats.recent >= r.emerging.trend_share * total
    just_emerged = (
        topic.state == "emerged"
        and topic.state_changed_at is not None
        and topic.state_changed_at >= now - timedelta(hours=r.emerging.emerged_recent_hours)
    )
    if surging or just_emerged:
        return "emerging"
    return None


def is_recent(topic: Topic, cfg: FrontParams, now: datetime) -> bool:
    return topic.updated_at >= now - timedelta(hours=cfg.ranking.recent_hours)


def support_and_reason(
    topic: Topic, stats: VoteStats, sources: int, cfg: FrontParams, now: datetime | None = None
) -> tuple[SupportOut, ReasonOut] | None:
    """(support, reason) of a topic for the front page, or None when it has no reason to be there."""
    now = now or datetime.now(UTC)
    support = SupportOut(level=level_for(stats, cfg), votes_count=stats.total)
    code = reason_code(topic, stats, sources, cfg, now)
    if code is None and stats.total < cfg.ranking.min_votes and is_recent(topic, cfg, now):
        code = "emerging"  # documented default: a recent topic not yet judged
    if code is None:
        return None
    return support, ReasonOut(code=code, label=REASON_LABELS[code])

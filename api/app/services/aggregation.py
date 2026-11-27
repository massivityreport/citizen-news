"""Aggregation of the citizens' unes into a ranking: THE function behind both the closing and the admin preview.

`aggregate` writes nothing. For an edition day it computes
- the participants: accounts with at least one topic in their une for that day (an empty une has no row),
- the score of every topic that is eligible AT THAT MOMENT (`eligible_pool(session, now)`: a topic that left the
  pool does not count, even if it is in some unes) = number of accounts that have it; only scores >= 1 are ranked,
- the ranking: score desc, then source_count desc, then updated_at desc (most recent first), then id asc
  (deterministic); the first `top` form the une, the next `extra` the "next" list of the admin preview,
- the tie information: groups of topics with the same score, the criterion that ordered them, and whether the
  group straddles the cut between the last place of the une and the first outside it,
- the publication data of every ranked topic (title, summary, sources, counts, image), captured from the very same
  reading, plus the proportion = score / participants.

Constant number of queries (pool, participants+scores in one statement, topics, cards): none per topic.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import MAX_UNE_TOPICS, Selection, Topic
from app.services.pool import eligible_pool
from app.services.topics import build_cards

Criterion = Literal["source_count", "updated_at", "id"]
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DEPTH: dict[Criterion, int] = {"source_count": 0, "updated_at": 1, "id": 2}


@dataclass(frozen=True)
class RankedTopic:
    rank: int
    topic_id: int
    score: int  # approvals
    proportion: float  # score / participants (exact, not rounded)
    # Captured publication data (copied as is into edition_topics at closing).
    title: str
    summary: str
    sources: list[dict]  # [{name, url, title, published_at: ISO string | None}]
    source_count: int
    article_count: int
    image_url: str | None
    updated_at: datetime
    tied_with: list[int] = field(default_factory=list)  # other topics with the same score
    broken_by: Criterion | None = None  # deepest criterion needed to order its tie group; None when alone


@dataclass(frozen=True)
class TieGroup:
    approvals: int
    topic_ids: list[int]  # in ranking order
    broken_by: Criterion
    crosses_cut: bool  # the group has topics inside and outside the une


@dataclass(frozen=True)
class Aggregation:
    edition_date: date
    computed_at: datetime
    participants: int
    top: int
    ranking: list[RankedTopic]  # every topic with score >= 1, best first
    ties: list[TieGroup]
    extra: int = 10

    @property
    def topics(self) -> list[RankedTopic]:
        """The une: ranks 1..top."""
        return self.ranking[: self.top]

    @property
    def next(self) -> list[RankedTopic]:
        """The runners-up: ranks top+1..top+extra (the preview of the admin)."""
        return self.ranking[self.top : self.top + self.extra]



def _decisive(a, b) -> Criterion:
    """The first criterion on which two consecutive topics of the same score differ."""
    if a.source_count != b.source_count:
        return "source_count"
    if a.updated_at != b.updated_at:
        return "updated_at"
    return "id"


def _micros(value: datetime) -> int:
    """Exact integer microseconds (a float timestamp would merge instants 1 µs apart): same resolution as the tie criterion."""
    return (value - _EPOCH) // timedelta(microseconds=1)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def aggregate(session: Session, edition_date: date, now: datetime, *, top: int = MAX_UNE_TOPICS, extra: int = 10) -> Aggregation:
    pool = {e.topic_id: e for e in eligible_pool(session, now)}
    # Participants and scores come from ONE statement (one snapshot): a concurrent write can never give a score
    # above the number of participants. GROUPING SETS: one row per topic, plus the grand total (topic_id NULL),
    # which is the number of distinct accounts with a non-empty une (it exists even with no selection: 0).
    participants = 0
    scores: dict[int, int] = {}
    for topic_id, count in session.execute(
        select(Selection.topic_id, func.count(func.distinct(Selection.account_id)))
        .where(Selection.edition_date == edition_date)
        .group_by(text("GROUPING SETS ((selections.topic_id), ())"))
    ):
        if topic_id is None:
            participants = count
        elif topic_id in pool:  # only topics eligible now count
            scores[topic_id] = count
    ordered = sorted(
        (pool[t] for t in scores),
        key=lambda e: (-scores[e.topic_id], -e.source_count, -_micros(e.updated_at), e.topic_id),
    )
    topics = {t.id: t for t in session.scalars(select(Topic).where(Topic.id.in_([e.topic_id for e in ordered])))} if ordered else {}
    ordered = [e for e in ordered if e.topic_id in topics]  # deleted in between: gone
    cards = {c.id: c for c in build_cards(session, [topics[e.topic_id] for e in ordered])}

    groups: dict[int, list[int]] = {}  # score -> positions in `ordered`, in order
    for position, e in enumerate(ordered):
        groups.setdefault(scores[e.topic_id], []).append(position)
    ties: list[TieGroup] = []
    tie_of: dict[int, tuple[list[int], Criterion]] = {}
    for score, positions in groups.items():
        if len(positions) < 2:
            continue
        broken_by = max(
            (_decisive(ordered[a], ordered[b]) for a, b in zip(positions, positions[1:])), key=lambda c: _DEPTH[c]
        )
        ids = [ordered[p].topic_id for p in positions]
        ties.append(TieGroup(score, ids, broken_by, positions[0] < top <= positions[-1]))
        for i in ids:
            tie_of[i] = (ids, broken_by)

    ranking = []
    for position, e in enumerate(ordered):
        card = cards[e.topic_id]
        others, broken_by = tie_of.get(e.topic_id, ([], None))
        ranking.append(
            RankedTopic(
                rank=position + 1,
                topic_id=e.topic_id,
                score=scores[e.topic_id],
                proportion=scores[e.topic_id] / participants,
                title=card.title,
                summary=card.summary,
                sources=[
                    {"name": s.name, "url": s.url, "title": s.title, "published_at": _iso(s.published_at)} for s in card.sources
                ],
                source_count=card.source_count,
                article_count=card.article_count,
                image_url=card.image_url,
                updated_at=card.updated_at,
                tied_with=[i for i in others if i != e.topic_id],
                broken_by=broken_by,
            )
        )
    return Aggregation(edition_date, now, participants, top, ranking, ties, extra)

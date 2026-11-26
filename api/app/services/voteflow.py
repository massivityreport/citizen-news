"""Which topics the vote flow (GET /api/vote/next) proposes, driven by the halving.

Categories (from topics.state / topics.wave):
  new      state `new` (wave 0): their first lot of votes
  rescue   state `reserve`: topics to re-evaluate
  near     `active` at the last wave (wave == waves-1): close to emerging
  active   `active` at the other waves: topics with traction
  emerged  only a last resort when nothing else is left (their evaluation is over)

Shares of the slots: new = new_topic_traffic_share, rescue = rescue_share, and the rest is split in two
equal halves between `near` and `active`. A request for `count` topics gets floor(count * share) slots per
category plus the remaining slots drawn at random with the fractional parts as weights (so the shares hold
on average even for count=1). A category with too few topics gives its unused slots to the others, in
proportion to their shares (equally if they all have a zero share). The final order is shuffled.

Inside a category, topics that still need votes come first (new: below the wave-0 quota; active: below
the quota of their next wave), at random. Reserve topics are drawn at random among the least recently
evaluated half. Never any result: this module only knows ids, states and counts.
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Topic, Vote
from app.services.halving import quota
from config.halving import HalvingParams

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
CATEGORIES = ("new", "rescue", "near", "active")


@dataclass(frozen=True)
class FlowTopic:
    id: int
    state: str
    wave: int
    votes: int = 0
    evaluated_at: datetime | None = None


def shares(params: HalvingParams) -> dict[str, float]:
    rest = max(0.0, 1.0 - params.new_topic_traffic_share - params.rescue_share)
    return {"new": params.new_topic_traffic_share, "rescue": params.rescue_share, "near": rest / 2, "active": rest / 2}


def _category(topic: FlowTopic, params: HalvingParams) -> str | None:
    if topic.state == "new":
        return "new"
    if topic.state == "reserve":
        return "rescue"
    if topic.state == "active":
        return "near" if topic.wave >= params.waves - 1 else "active"
    return None  # emerged: handled as a fallback


def _ordered(topics: list[FlowTopic], category: str, params: HalvingParams, rng: random.Random) -> list[int]:
    """Topic ids of one category in the order they will be proposed."""
    if category == "rescue":
        oldest = sorted(topics, key=lambda t: (t.evaluated_at or EPOCH, t.id))
        half = (len(oldest) + 1) // 2
        head, tail = oldest[:half], oldest[half:]
    else:
        head = [t for t in topics if t.votes < quota(params, t.wave)]
        tail = [t for t in topics if t.votes >= quota(params, t.wave)]
    ids = []
    for group in (head, tail):
        group_ids = sorted(t.id for t in group)  # sorted first: the shuffle only depends on the seed
        rng.shuffle(group_ids)
        ids += group_ids
    return ids


def select_flow(topics: list[FlowTopic], count: int, params: HalvingParams, rng: random.Random) -> list[int]:
    """Up to `count` topic ids, mixed according to the halving. `topics` must already exclude seen/voted ones."""
    by_category: dict[str, list[FlowTopic]] = {c: [] for c in CATEGORIES}
    emerged = []
    for t in topics:
        c = _category(t, params)
        if c is None:
            emerged.append(t)
        else:
            by_category[c].append(t)
    pools = {c: _ordered(by_category[c], c, params, rng) for c in CATEGORIES}
    pools["emerged"] = _ordered(emerged, "emerged", params, rng)

    weights = shares(params)
    # 1. guaranteed part: floor(count * share), then the leftover slots by fractional part
    targets = {c: count * weights[c] for c in CATEGORIES}
    slots = {c: int(targets[c] + 1e-9) for c in CATEGORIES}
    spare = count - sum(slots.values())
    while spare > 0:
        fractions = {c: max(targets[c] - slots[c], 0.0) for c in CATEGORIES}
        if sum(fractions.values()) <= 0:
            break
        pick = _weighted(fractions, rng)
        slots[pick] += 1
        spare -= 1
    chosen: list[int] = []
    for c in CATEGORIES:
        taken, pools[c] = pools[c][: slots[c]], pools[c][slots[c]:]
        chosen += taken
    # 2. categories that ran dry hand their slots to the others
    while len(chosen) < count:
        open_cats = {c: weights[c] for c in CATEGORIES if pools[c]}
        if open_cats:
            if sum(open_cats.values()) <= 0:
                open_cats = {c: 1.0 for c in open_cats}
            c = _weighted(open_cats, rng)
            chosen.append(pools[c].pop(0))
        elif pools["emerged"]:
            chosen.append(pools["emerged"].pop(0))
        else:
            break
    rng.shuffle(chosen)
    return chosen


def _weighted(weights: dict[str, float], rng: random.Random) -> str:
    keys = sorted(weights)  # fixed order: same seed, same result
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def flow_candidates(session: Session, eligible_ids, excluded: set[int]) -> list[FlowTopic]:
    """Eligible topics (a subquery of ids) minus `excluded`, with their vote counts."""
    # Count only the eligible topics' votes: the cost must not grow with the whole votes table.
    counts = (
        select(Vote.topic_id.label("topic_id"), func.count().label("n"))
        .where(Vote.topic_id.in_(select(eligible_ids.c.id)))
        .group_by(Vote.topic_id)
        .subquery()
    )
    query = (
        select(Topic.id, Topic.state, Topic.wave, func.coalesce(counts.c.n, 0), Topic.evaluated_at)
        .join(eligible_ids, eligible_ids.c.id == Topic.id)
        .outerjoin(counts, counts.c.topic_id == Topic.id)
        .order_by(Topic.id)
    )
    if excluded:
        query = query.where(Topic.id.not_in(excluded))
    return [FlowTopic(i, s, w, n, e) for i, s, w, n, e in session.execute(query)]

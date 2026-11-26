"""Successive Halving: which topics keep being shown, which emerge, which wait in reserve.

Vocabulary. A topic is `new` (wave 0, never evaluated), `active` (cleared at least one wave),
`reserve` (eliminated, may come back) or `emerged` (cleared all `waves` waves). `topics.wave` is the
number of waves cleared so far (for a `reserve` topic: the wave where it was eliminated).

Score. Only votes of accounts count (table `votes`). score = lower bound of the Wilson interval (z=1.96)
of the share of "more" among the OPINIONS (`more` + `not_priority`). "unknown" is not an opinion, so it
never moves the share, but it counts in the total number of votes. The lower bound keeps a small
sample from beating a large one: 15 "more" out of 20 (0.53) ranks above 3 out of 3 (0.44). A topic with no
opinion in favour (score 0) is never promoted.

Waves. The quota of wave w is `min_votes_first_decision * 2**w` TOTAL votes (cumulative: 20, 40, 80 with
the defaults): the bar rises at each wave, so votes concentrate on fewer and fewer topics.

Selection, wave by wave (w = 0 .. waves-1, in that order, in one run):
  1. candidates = topics at wave w (`new`/`active`) whose total votes reached quota(w), plus `reserve`
     topics of wave w that received a fresh batch of `min_votes_first_decision` votes since their last
     evaluation (rescue, see below);
  2. peers = every other topic already evaluated at this wave (votes >= quota(w), wave >= w, not `new`);
  3. rank candidates and peers together by score (ties: lower id first) and keep the best
     ceil(keep_ratio * size) (at least 1). A candidate inside that top is promoted (wave w+1, `active`,
     or `emerged` after `waves` waves); the others go to `reserve` (wave unchanged).
  Peers are never demoted or promoted by this: they only make the comparison fair when a late topic
  reaches its quota alone (without peers a lone candidate would always be "the best half").

Rescue. The vote flow reserves `rescue_share` of its slots for `reserve` topics (random among the least
recently evaluated, see voteflow.py). Once a reserve topic has `min_votes_first_decision` new votes, it is a
candidate again at its wave, scored on all its votes. Nothing is ever final: a topic back in the top is promoted.

Determinism. `decide` is a pure function of (votes, state, now): same input, same output, no randomness.
Running it again right after changes nothing (idempotent): winners and losers are no longer candidates.
Only `halve` touches the database; it never writes `topics.updated_at` (the freshness of the topic).

Runs in the worker (`python -m app.cli halve`), never in a vote request.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.entities import Topic, Vote
from config.halving import HalvingParams, load_halving_params

WILSON_Z = 1.96
EVALUATED_STATES = ("active", "reserve", "emerged")


def wilson_lower_bound(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Lower bound of the Wilson score interval for a proportion (0.0 when there is no sample)."""
    if total <= 0:
        return 0.0
    p = successes / total
    z2 = z * z
    centre = p + z2 / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))
    return max(0.0, (centre - margin) / (1 + z2 / total))


def quota(params: HalvingParams, wave: int) -> int:
    """Total votes a topic needs to be evaluated at `wave`."""
    return params.min_votes_first_decision * 2**wave


@dataclass(frozen=True)
class TopicVotes:
    id: int
    state: str = "new"
    wave: int = 0
    more: int = 0
    not_priority: int = 0
    unknown: int = 0
    votes_at_eval: int = 0
    evaluated_at: datetime | None = None
    state_changed_at: datetime | None = None

    @property
    def votes(self) -> int:
        return self.more + self.not_priority + self.unknown

    @property
    def score(self) -> float:
        return wilson_lower_bound(self.more, self.more + self.not_priority)


def keep_count(params: HalvingParams, size: int) -> int:
    return max(1, math.ceil(round(params.keep_ratio * size, 9)))


def decide(topics: list[TopicVotes], params: HalvingParams, now: datetime) -> list[TopicVotes]:
    """Topics whose (state, wave, evaluation bookkeeping) change, with their new values. Pure."""
    original = {t.id: t for t in topics}
    current = dict(original)
    for wave in range(params.waves):
        needed = quota(params, wave)
        candidates, peers = [], []
        for t in current.values():
            if t.votes < needed:
                continue
            fresh_batch = t.votes - t.votes_at_eval >= params.min_votes_first_decision
            if t.wave == wave and (t.state in ("new", "active") or (t.state == "reserve" and fresh_batch)):
                candidates.append(t)
            elif t.state in EVALUATED_STATES and t.wave >= wave:
                peers.append(t)
        if not candidates:
            continue
        ranking = sorted(candidates + peers, key=lambda t: (-t.score, t.id))
        winners = {t.id for t in ranking[: keep_count(params, len(ranking))]}
        for t in candidates:
            if t.id in winners and t.score > 0:
                new_wave = wave + 1
                new_state = "emerged" if new_wave >= params.waves else "active"
            else:
                new_wave, new_state = wave, "reserve"
            changed = (new_state, new_wave) != (t.state, t.wave)
            current[t.id] = TopicVotes(
                id=t.id, state=new_state, wave=new_wave, more=t.more, not_priority=t.not_priority,
                unknown=t.unknown, votes_at_eval=t.votes, evaluated_at=now,
                state_changed_at=now if changed else t.state_changed_at,
            )
    return [t for t in current.values() if t != original[t.id]]


@dataclass
class HalvingReport:
    evaluated: int = 0   # topics whose decision was (re)taken
    promoted: int = 0
    demoted: int = 0
    emerged: int = 0


def load_topic_votes(session: Session) -> list[TopicVotes]:
    counts = (
        select(
            Vote.topic_id.label("topic_id"),
            func.count().filter(Vote.choice == "more").label("more"),
            func.count().filter(Vote.choice == "not_priority").label("not_priority"),
            func.count().filter(Vote.choice == "unknown").label("unknown"),
        )
        .group_by(Vote.topic_id)
        .subquery()
    )
    rows = session.execute(
        select(
            Topic.id, Topic.state, Topic.wave, Topic.votes_at_eval, Topic.evaluated_at, Topic.state_changed_at,
            func.coalesce(counts.c.more, 0), func.coalesce(counts.c.not_priority, 0), func.coalesce(counts.c.unknown, 0),
        )
        .outerjoin(counts, counts.c.topic_id == Topic.id)
        .order_by(Topic.id)
    )
    return [
        TopicVotes(id=i, state=s, wave=w, votes_at_eval=v, evaluated_at=e, state_changed_at=c, more=m, not_priority=n, unknown=u)
        for i, s, w, v, e, c, m, n, u in rows
    ]


def halve(session: Session, params: HalvingParams | None = None, now: datetime | None = None) -> HalvingReport:
    """Recompute states and waves from the votes and store them. Idempotent. Never touches `updated_at`."""
    params = params or load_halving_params()
    now = now or datetime.now(UTC)
    before = {t.id: t for t in load_topic_votes(session)}
    report = HalvingReport()
    for new in decide(list(before.values()), params, now):
        old = before[new.id]
        if new.evaluated_at != old.evaluated_at:
            report.evaluated += 1
        if (new.state, new.wave) != (old.state, old.wave):
            if new.state == "reserve":
                report.demoted += 1
            else:
                report.promoted += 1
                report.emerged += new.state == "emerged"
        session.execute(
            update(Topic)
            .where(Topic.id == new.id)
            .values(
                state=new.state, wave=new.wave, evaluated_at=new.evaluated_at,
                votes_at_eval=new.votes_at_eval, state_changed_at=new.state_changed_at,
            )
        )
    session.commit()
    return report

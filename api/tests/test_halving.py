from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Topic
from app.services.halving import TopicVotes, decide, halve, keep_count, quota, wilson_lower_bound
from config.halving import HalvingParams
from tests.helpers import add_votes

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
P = HalvingParams()  # 20 votes, keep 0.5, 3 waves


def tv(id, more, not_priority=0, unknown=0, **kw):
    return TopicVotes(id=id, more=more, not_priority=not_priority, unknown=unknown, **kw)


def run(topics, params=P, now=NOW):
    """Apply decide() and return {id: (state, wave)} for all topics."""
    changed = {t.id: t for t in decide(topics, params, now)}
    return {t.id: (changed.get(t.id, t).state, changed.get(t.id, t).wave) for t in topics}


def test_wilson_prefers_large_sample_over_tiny_perfect_one():
    assert wilson_lower_bound(15, 20) > wilson_lower_bound(3, 3)
    assert wilson_lower_bound(0, 0) == 0.0
    assert 0 < wilson_lower_bound(3, 3) < 1


def test_quota_doubles_each_wave():
    assert [quota(P, w) for w in range(3)] == [20, 40, 80]


def test_no_decision_before_min_votes():
    topics = [tv(1, 19), tv(2, 10, 5, 4), tv(3, 0, 18)]
    assert decide(topics, P, NOW) == []


def test_first_wave_keeps_keep_ratio_of_the_best():
    topics = [tv(i, more=20 - i, not_priority=i) for i in range(10)]  # id 0 best ... id 9 worst
    out = run(topics)
    assert [i for i, s in out.items() if s == ("active", 1)] == [0, 1, 2, 3, 4]
    assert [i for i, s in out.items() if s == ("reserve", 0)] == [5, 6, 7, 8, 9]


def test_smoothed_score_favours_15_of_20_over_3_of_3():
    topics = [tv(1, 3, 0, 17), tv(2, 15, 5)]  # both have 20 votes; topic 1 has 3 opinions, all "more"
    out = run(topics)
    assert out[2] == ("active", 1) and out[1] == ("reserve", 0)


def test_unknown_counts_in_total_but_is_not_an_opinion():
    # 20 votes, of which 5 "more" and 15 "unknown": reaches the quota; its score only uses the 5 opinions
    topic = tv(1, 5, 0, 15)
    assert topic.votes == 20
    assert topic.score == wilson_lower_bound(5, 5)
    assert tv(2, 10, 10).score < topic.score


def test_topic_without_support_is_never_promoted_even_alone():
    assert run([tv(1, 0, 20)]) == {1: ("reserve", 0)}
    assert run([tv(1, 0, 0, 20)]) == {1: ("reserve", 0)}


def test_acceleration_next_wave_needs_a_doubled_quota():
    # wave 1 topic with 39 votes: not decided; with 40: decided
    waiting = tv(1, 30, 9, state="active", wave=1)
    assert decide([waiting], P, NOW) == []
    assert run([tv(1, 30, 10, state="active", wave=1)]) == {1: ("active", 2)}


def test_emergence_after_all_waves_cleared():
    assert run([tv(1, 80, 0)]) == {1: ("emerged", 3)}  # cascades through the three quotas in one run
    assert run([tv(1, 60, 0)]) == {1: ("active", 2)}   # 60 votes clear waves 0 and 1 only
    assert run([tv(1, 20, 0)], HalvingParams(waves=1)) == {1: ("emerged", 1)}


def test_late_candidate_is_compared_with_the_topics_already_evaluated():
    peers = [tv(i, 18, 2, state="active", wave=1) for i in range(1, 5)]
    peers += [tv(i, 8, 12, state="reserve", wave=0) for i in range(5, 9)]
    # a mediocre latecomer must not pass just because it is alone
    assert run(peers + [tv(9, 7, 13)])[9] == ("reserve", 0)
    assert run(peers + [tv(9, 20, 0)])[9] == ("active", 1)


def test_rescue_reserve_topic_with_fresh_votes_is_reevaluated():
    reserve = dict(state="reserve", wave=0, votes_at_eval=20)
    peers = [tv(i, 14, 6, state="active", wave=1, votes_at_eval=20) for i in range(1, 5)]
    # no fresh batch yet: unchanged
    assert decide(peers + [tv(9, 22, 0, **reserve)], P, NOW) == []
    # 20 new votes, now excellent: promoted back
    topics = peers + [tv(9, 40, 0, **reserve)]
    assert run(topics)[9][0] in ("active", "emerged")
    # 20 new votes but still weak: stays in reserve, evaluation time and baseline refreshed, not condemned
    weak = tv(9, 8, 32, **reserve)
    (after,) = decide(peers + [weak], P, NOW)
    assert (after.state, after.wave, after.evaluated_at, after.votes_at_eval) == ("reserve", 0, NOW, 40)


def test_idempotent():
    topics = [tv(i, more=40 - i, not_priority=i % 7, unknown=i % 3) for i in range(12)]
    first = {t.id: t for t in decide(topics, P, NOW)}
    settled = [first.get(t.id, t) for t in topics]
    assert decide(settled, P, NOW + timedelta(hours=1)) == []


def test_deterministic_regardless_of_input_order():
    topics = [tv(i, more=15 + (i * 7) % 6, not_priority=5 - (i * 7) % 6) for i in range(9)]
    assert run(topics) == run(list(reversed(topics)))


@pytest.mark.parametrize(
    "ratio, size, expected",
    [(0.5, 10, 5), (0.5, 3, 2), (0.3, 10, 3), (0.01, 10, 1), (0.99, 10, 10), (0.5, 1, 1)],
)
def test_keep_count(ratio, size, expected):
    assert keep_count(HalvingParams(keep_ratio=ratio), size) == expected


def test_extreme_parameters():
    topics = [tv(i, more=10 - i, not_priority=i) for i in range(6)]
    strict = run(topics, HalvingParams(min_votes_first_decision=10, keep_ratio=0.01, waves=10))
    assert [i for i, s in strict.items() if s[0] == "active"] == [0]  # one survivor, never zero
    lax = run(topics, HalvingParams(min_votes_first_decision=10, keep_ratio=0.99, waves=1))
    assert [i for i, s in lax.items() if s[0] == "emerged"] == [0, 1, 2, 3, 4, 5]
    # min_votes=1, waves=10: quota(w) = 2**w, so one vote clears wave 0 only; a lone "not_priority" is reserved
    tiny = HalvingParams(min_votes_first_decision=1, waves=10)
    assert run([tv(1, 1), tv(2, 0, 1)], tiny) == {1: ("active", 1), 2: ("reserve", 0)}


# --- database ---


def make_topics(session, n):
    topics = [Topic(title=f"Sujet {i}", updated_at=NOW - timedelta(hours=i + 1)) for i in range(n)]
    session.add_all(topics)
    session.flush()
    return topics


def snapshot(session):
    session.expire_all()
    return {t.id: (t.state, t.wave, t.updated_at, t.evaluated_at, t.votes_at_eval) for t in session.scalars(select(Topic))}


def test_halve_stores_states_and_never_touches_updated_at(session):
    topics = make_topics(session, 4)
    for t, (m, n) in zip(topics, [(18, 2), (15, 5), (6, 14), (3, 17)]):
        add_votes(session, t, more=m, not_priority=n)
    session.commit()
    freshness = {t.id: t.updated_at for t in topics}

    report = halve(session, P, NOW)
    after = snapshot(session)
    assert (report.promoted, report.demoted) == (2, 2)
    assert [after[t.id][:2] for t in topics] == [("active", 1), ("active", 1), ("reserve", 0), ("reserve", 0)]
    assert {i: row[2] for i, row in after.items()} == freshness  # freshness intact
    assert all(row[3] == NOW and row[4] == 20 for row in after.values())
    changed_at = session.scalar(select(Topic.state_changed_at).where(Topic.id == topics[0].id))
    assert changed_at == NOW


def test_halve_is_idempotent_in_database(session):
    topics = make_topics(session, 6)
    for i, t in enumerate(topics):
        add_votes(session, t, more=30 - 4 * i, not_priority=4 * i, unknown=i)
    session.commit()
    halve(session, P, NOW)
    first = snapshot(session)
    report = halve(session, P, NOW + timedelta(hours=1))
    assert snapshot(session) == first
    assert (report.evaluated, report.promoted, report.demoted) == (0, 0, 0)


def test_unrelated_topic_updates_still_let_the_clustering_set_updated_at(session):
    topic = make_topics(session, 1)[0]
    session.commit()
    later = NOW + timedelta(days=1)
    topic.updated_at = later
    session.commit()
    session.refresh(topic)
    assert topic.updated_at == later  # explicit value is honoured (no onupdate overriding it)
    topic.title = "Autre titre"  # and a plain update does not silently bump freshness either
    session.commit()
    session.refresh(topic)
    assert topic.updated_at == later

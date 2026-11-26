import random
from collections import Counter

import pytest

from app.deps import SESSION_COOKIE
from app.routers.topics import get_flow_rng
from app.services.voteflow import FlowTopic, select_flow, shares
from config.halving import HalvingParams
from tests.helpers import add_votes, make_sources, make_topic

P = HalvingParams()  # new 0.30, rescue 0.10, waves 3


def pool(new=0, reserve=0, active=0, near=0, emerged=0):
    topics, n = [], 0
    for state, wave, how_many in (("new", 0, new), ("reserve", 0, reserve), ("active", 1, active), ("active", 2, near), ("emerged", 3, emerged)):
        for _ in range(how_many):
            n += 1
            topics.append(FlowTopic(n, state, wave))
    return topics


def kinds(topics, ids):
    by_id = {t.id: ("near" if t.wave == 2 else t.state if t.state != "active" else "active") for t in topics}
    return Counter(by_id[i] for i in ids)


def test_shares_sum_to_one_and_split_the_rest_in_two():
    s = shares(P)
    assert s == pytest.approx({"new": 0.3, "rescue": 0.1, "near": 0.3, "active": 0.3})


def test_proportions_over_a_large_sample_with_fixed_seed():
    topics = pool(new=200, reserve=200, active=200, near=200)
    rng = random.Random(1234)
    total = Counter()
    for _ in range(2000):
        total += kinds(topics, select_flow(topics, 10, P, rng))
    n = sum(total.values())
    assert n == 20000
    assert total["new"] / n == pytest.approx(0.30, abs=0.015)
    assert total["reserve"] / n == pytest.approx(0.10, abs=0.015)
    assert total["near"] / n == pytest.approx(0.30, abs=0.015)
    assert total["active"] / n == pytest.approx(0.30, abs=0.015)


def test_shares_hold_on_average_even_one_topic_at_a_time():
    topics = pool(new=50, reserve=50, active=50, near=50)
    rng = random.Random(7)
    total = Counter()
    for _ in range(4000):
        total += kinds(topics, select_flow(topics, 1, P, rng))
    assert total["reserve"] / 4000 == pytest.approx(0.10, abs=0.02)
    assert total["new"] / 4000 == pytest.approx(0.30, abs=0.03)


def test_same_seed_same_flow_and_order_is_shuffled():
    topics = pool(new=30, reserve=30, active=30, near=30)
    a = select_flow(topics, 10, P, random.Random(5))
    assert a == select_flow(topics, 10, P, random.Random(5))
    assert a != select_flow(topics, 10, P, random.Random(6))
    orders = {tuple(kinds_in_order(topics, select_flow(topics, 10, P, random.Random(s)))) for s in range(30)}
    assert len(orders) > 5  # categories are not served in a fixed sequence


def kinds_in_order(topics, ids):
    by_id = {t.id: t.state + str(t.wave) for t in topics}
    return [by_id[i] for i in ids]


@pytest.mark.parametrize("empty", ["new", "reserve", "active", "near"])
def test_empty_category_is_redistributed(empty):
    sizes = dict(new=40, reserve=40, active=40, near=40)
    sizes[empty] = 0
    topics = pool(**sizes)
    for seed in range(20):
        ids = select_flow(topics, 10, P, random.Random(seed))
        assert len(ids) == 10 and len(set(ids)) == 10
        assert kinds(topics, ids)[empty] == 0


def test_flow_with_a_single_category_and_fewer_topics_than_asked():
    topics = pool(new=4)
    assert sorted(select_flow(topics, 10, P, random.Random(0))) == [1, 2, 3, 4]
    assert select_flow([], 10, P, random.Random(0)) == []


def test_emerged_topics_only_when_nothing_else_is_left():
    topics = pool(new=2, emerged=5)
    ids = select_flow(topics, 5, P, random.Random(0))
    assert len(ids) == 5 and {1, 2} <= set(ids)
    plenty = select_flow(pool(new=10, emerged=5), 5, P, random.Random(0))
    assert len(plenty) == 5 and max(plenty) <= 10  # ids 11-15 are the emerged ones


def test_topics_below_their_quota_come_first():
    needy = [FlowTopic(i, "new", 0, votes=5) for i in range(1, 6)]
    done = [FlowTopic(i, "new", 0, votes=25) for i in range(6, 16)]
    for seed in range(20):
        ids = select_flow(needy + done, 5, HalvingParams(new_topic_traffic_share=1, rescue_share=0), random.Random(seed))
        assert sorted(ids) == [1, 2, 3, 4, 5]


def test_rescue_draws_among_the_least_recently_evaluated():
    from datetime import UTC, datetime, timedelta

    base = datetime(2026, 11, 1, tzinfo=UTC)
    reserve = [FlowTopic(i, "reserve", 0, evaluated_at=base + timedelta(days=i)) for i in range(1, 11)]
    only_rescue = HalvingParams(new_topic_traffic_share=0, rescue_share=1)
    seen = set()
    for seed in range(50):
        ids = select_flow(reserve, 3, only_rescue, random.Random(seed))
        assert set(ids) <= {1, 2, 3, 4, 5}  # oldest half
        seen |= set(ids)
    assert seen == {1, 2, 3, 4, 5}  # random inside that half


def test_extreme_shares():
    topics = pool(new=20, reserve=20, active=20, near=20)
    only_new = select_flow(topics, 10, HalvingParams(new_topic_traffic_share=1, rescue_share=0), random.Random(0))
    assert kinds(topics, only_new) == Counter(new=10)
    none_new = select_flow(topics, 10, HalvingParams(new_topic_traffic_share=0, rescue_share=0), random.Random(0))
    assert kinds(topics, none_new)["new"] == 0 and kinds(topics, none_new)["reserve"] == 0


# --- GET /api/vote/next ---

CARD_KEYS = {"id", "title", "summary", "sources", "first_seen_at", "updated_at", "image_url"}


@pytest.fixture
def world(session):
    a, b = make_sources(session, "Média A", "Média B")
    made = {
        "new": [make_topic(session, f"Nouveau {i}", [a, b]) for i in range(6)],
        "reserve": [make_topic(session, f"Réserve {i}", [a, b], state="reserve") for i in range(4)],
        "active": [make_topic(session, f"Actif {i}", [a, b], state="active", wave=1) for i in range(4)],
        "near": [make_topic(session, f"Proche {i}", [a, b], state="active", wave=2) for i in range(4)],
    }
    make_topic(session, "Un seul média", [a])  # not eligible
    session.commit()
    return made


def ids_of(response):
    return [i["id"] for i in response.json()["items"]]


def test_vote_next_mixes_categories_and_exposes_no_result(client, world):
    client.app.dependency_overrides[get_flow_rng] = lambda: random.Random(3)
    r = client.get("/api/vote/next?count=10")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 10
    assert all(set(i) == CARD_KEYS for i in items)  # no support, no reason, no counter
    wanted = {t.id: k for k, ts in world.items() for t in ts}
    assert {wanted[i["id"]] for i in items} == {"new", "reserve", "active", "near"}
    assert "Un seul média" not in {i["title"] for i in items}


def test_vote_next_excludes_seen_and_voted(logged, world, session):
    everything = [t.id for ts in world.values() for t in ts]
    add_votes(session, world["new"][0], more=3, prefix="other")  # votes of others do not matter
    session.commit()
    voted = everything[:5]
    from app.models import Vote

    session.add_all(Vote(account_id=logged.account_id, topic_id=t, choice="more") for t in voted)
    session.commit()
    seen = everything[5:8]
    got = ids_of(logged.get(f"/api/vote/next?count=20&seen={','.join(map(str, seen))}"))
    assert set(got) == set(everything) - set(voted) - set(seen)
    assert len(got) == len(set(got))


def test_vote_next_works_without_session(client, world):
    assert len(ids_of(client.get("/api/vote/next?count=5"))) == 5


def test_vote_next_with_an_invalid_session_cookie_behaves_as_anonymous(client, world):
    client.cookies.set(SESSION_COOKIE, "not-a-session")
    assert len(ids_of(client.get("/api/vote/next?count=5"))) == 5


def test_vote_next_when_only_one_category_exists(client, session):
    a, b = make_sources(session, "A", "B")
    for i in range(3):
        make_topic(session, f"Nouveau {i}", [a, b])
    session.commit()
    assert len(ids_of(client.get("/api/vote/next?count=10"))) == 3
    assert ids_of(client.get("/api/vote/next?seen=1,2,3")) == []


def test_vote_next_validation(client, world):
    assert client.get("/api/vote/next?count=0").status_code == 422
    assert client.get("/api/vote/next?seen=a").status_code == 422


def test_vote_counts_come_from_eligible_topics_only(world, session):
    from sqlalchemy import select

    from app.models import Topic
    from app.services.topics import eligible_topics
    from app.services.voteflow import flow_candidates
    from config.clustering import load_clustering_params

    add_votes(session, world["new"][0], more=4)
    add_votes(session, world["reserve"][0], more=2, not_priority=1)
    add_votes(session, session.scalar(select(Topic).where(Topic.title == "Un seul média")), more=9)  # not eligible
    session.commit()
    eligible = eligible_topics(load_clustering_params()).subquery()
    found = {t.id: t.votes for t in flow_candidates(session, eligible, set())}
    assert found[world["new"][0].id] == 4 and found[world["reserve"][0].id] == 3
    assert found[world["new"][1].id] == 0 and len(found) == 18

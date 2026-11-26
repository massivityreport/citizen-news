from datetime import UTC, datetime, timedelta

import pytest

from app.models import Topic
from app.services.support import VoteStats, level_for, reason_code, support_and_reason
from config.front import FrontParams, load_front_params
from tests.helpers import add_votes, make_sources, make_topic

CFG = FrontParams()
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def topic(**kw):
    values = dict(id=1, title="t", state="active", wave=1, updated_at=NOW - timedelta(hours=30))
    return Topic(**{**values, **kw})


# --- pure rules ---


@pytest.mark.parametrize(
    "stats, level",
    [
        (VoteStats(), "low"),
        (VoteStats(more=9), "low"),                      # too few votes
        (VoteStats(more=10), "medium"),
        (VoteStats(more=12, not_priority=28), "low"),    # enough votes, weak score
        (VoteStats(more=29), "medium"),                  # score fine, below the high minimum of 30 votes
        (VoteStats(more=30), "high"),
        (VoteStats(more=40, not_priority=20, unknown=100), "high"),  # "unknown" counts in the total only
    ],
)
def test_level(stats, level):
    assert level_for(stats, CFG) == level


def test_votes_count_includes_unknown():
    support, _ = support_and_reason(topic(), VoteStats(more=55, unknown=5), 3, CFG, NOW)
    assert support.votes_count == 60


@pytest.mark.parametrize(
    "stats, sources, expected",
    [
        (VoteStats(more=60), 3, "common_priority"),
        (VoteStats(more=60), 2, "common_priority"),              # strong and broad wins over the radar
        (VoteStats(more=20, not_priority=1), 2, "under_the_radar"),
        (VoteStats(more=20, not_priority=1), 3, None),            # medium support, many media, nothing special
        (VoteStats(more=35, not_priority=30), 4, "strong_mobilisation"),
        (VoteStats(more=35, not_priority=100), 4, None),          # many "more", but no real support
        (VoteStats(more=12, recent=12), 4, "emerging"),           # votes surging
        (VoteStats(more=12, recent=6), 4, None),
        (VoteStats(more=25, recent=12), 4, None),                 # recent votes are a small share of the total
        (VoteStats(more=3, recent=3), 4, None),
    ],
)
def test_reason_code(stats, sources, expected):
    assert reason_code(topic(), stats, sources, CFG, NOW) == expected


def test_recently_emerged_topic_is_emerging():
    stats = VoteStats(more=20)
    fresh = topic(state="emerged", wave=3, state_changed_at=NOW - timedelta(hours=5))
    old = topic(state="emerged", wave=3, state_changed_at=NOW - timedelta(days=5))
    assert reason_code(fresh, stats, 4, CFG, NOW) == "emerging"
    assert reason_code(old, stats, 4, CFG, NOW) is None


def test_no_minority_alert_nor_cross_cutting_priority_in_v1():
    from app.services.support import REASON_LABELS

    assert set(REASON_LABELS) == {"common_priority", "strong_mobilisation", "under_the_radar", "emerging"}


def test_recent_unjudged_topic_gets_the_documented_default_reason():
    recent = topic(updated_at=NOW - timedelta(hours=2))
    support, reason = support_and_reason(recent, VoteStats(), 3, CFG, NOW)
    assert (support.level, support.votes_count, reason.code, reason.label) == ("low", 0, "emerging", "Sujet émergent")
    assert support_and_reason(topic(), VoteStats(), 3, CFG, NOW) is None  # old and unvoted: no reason, no front page
    assert support_and_reason(recent, VoteStats(not_priority=30), 3, CFG, NOW) is None  # judged: no default


def test_front_config_is_validated(tmp_path):
    assert load_front_params().ranking.min_votes == 10
    for bad in ("support: {high_score: 0.1}", "ranking: {support_weight: 0, freshness_weight: 0}", "bogus: 1",
                "reasons: {emerging: {trend_share: 0}}"):
        path = tmp_path / "f.yaml"
        path.write_text(bad)
        with pytest.raises(Exception):
            load_front_params(path)


# --- GET /api/topics/front ---


@pytest.fixture
def world(session):
    a, b, c = make_sources(session, "Média A", "Média B", "Média C")
    t = {}
    t["priority"] = make_topic(session, "Priorité", [a, b, c], hours_ago=20)
    t["mobilised"] = make_topic(session, "Mobilisation", [a, b, c], hours_ago=20)
    t["radar"] = make_topic(session, "Radar", [a, b], hours_ago=20)
    t["fresh"] = make_topic(session, "Fraîche", [a, b], hours_ago=1)
    t["rejected"] = make_topic(session, "Rejetée", [a, b, c], hours_ago=2)
    t["reserve"] = make_topic(session, "Réserve", [a, b, c], hours_ago=1, state="reserve")
    t["old"] = make_topic(session, "Ancienne", [a, b, c], hours_ago=30)
    t["single"] = make_topic(session, "Un seul média", [a], hours_ago=20)
    add_votes(session, t["priority"], more=70, not_priority=5)
    add_votes(session, t["mobilised"], more=40, not_priority=30)
    add_votes(session, t["radar"], more=18, not_priority=2)
    add_votes(session, t["rejected"], more=3, not_priority=30)
    add_votes(session, t["reserve"], more=80)
    add_votes(session, t["single"], more=16, not_priority=2)  # under the radar needs <= 2 media: 1 medium qualifies
    session.commit()
    return t


def front(client, limit=20):
    return client.get(f"/api/topics/front?limit={limit}").json()["items"]


def test_front_reasons_and_membership(client, world):
    by_title = {i["title"]: i for i in front(client)}
    assert {k: (v["reason"]["code"], v["support"]["level"]) for k, v in by_title.items()} == {
        "Priorité": ("common_priority", "high"),
        "Mobilisation": ("strong_mobilisation", "medium"),
        "Radar": ("under_the_radar", "medium"),  # 20 votes: below the 30 needed for high
        "Fraîche": ("emerging", "low"),
        "Un seul média": ("under_the_radar", "medium"),  # a single medium is allowed on the front when under the radar
    }
    # reserve, old unvoted, and judged-and-rejected topics are out
    assert by_title["Priorité"]["support"]["votes_count"] == 75
    assert by_title["Priorité"]["reason"]["label"] == "Priorité commune"


def test_front_every_card_has_a_reason_and_the_contract_shape(client, world):
    for item in front(client):
        assert item["reason"]["code"] and item["reason"]["label"]
        assert set(item["support"]) == {"level", "votes_count"}


def test_front_ranks_support_and_freshness_together(client, world):
    titles = [i["title"] for i in front(client)]
    assert titles[0] == "Priorité"  # strongest score, still fairly fresh
    assert titles.index("Radar") < titles.index("Fraîche")  # a high score beats pure freshness
    # a fresh topic with no votes at all still shows up
    assert "Fraîche" in titles


def test_front_freshness_matters_when_support_is_equal(client, session):
    a, b = make_sources(session, "A", "B")
    older = make_topic(session, "Plus ancien", [a, b], hours_ago=8)
    newer = make_topic(session, "Plus récent", [a, b], hours_ago=1)
    for t in (older, newer):
        add_votes(session, t, more=20, not_priority=2)
    session.commit()
    assert [i["title"] for i in front(client)] == ["Plus récent", "Plus ancien"]


def test_front_limit(client, world):
    assert len(front(client, 2)) == 2


def test_front_default_limit_is_10_and_has_more(client, session):
    a, b = make_sources(session, "A", "B")
    for i in range(12):
        add_votes(session, make_topic(session, f"Sujet {i}", [a, b], hours_ago=1 + i), more=20, not_priority=2)
    session.commit()
    body = client.get("/api/topics/front").json()
    assert len(body["items"]) == 10 and body["has_more"] is True
    body = client.get("/api/topics/front?limit=12").json()
    assert len(body["items"]) == 12 and body["has_more"] is False
    body = client.get("/api/topics/front?limit=50").json()
    assert len(body["items"]) == 12 and body["has_more"] is False


def test_front_has_more_is_false_when_exactly_limit(client, world):
    n = len(front(client, 50))
    assert client.get(f"/api/topics/front?limit={n}").json()["has_more"] is False
    assert client.get(f"/api/topics/front?limit={n - 1}").json()["has_more"] is True


def test_front_limit_is_a_prefix_without_duplicates(session):
    from app.services.front import front_topics
    from config.clustering import load_clustering_params

    a, b = make_sources(session, "A", "B")
    for i in range(25):
        add_votes(session, make_topic(session, f"Sujet {i}", [a, b], hours_ago=1 + i % 7), more=10 + i, not_priority=2)
    session.commit()
    now = datetime.now(UTC)
    ids = lambda n: [t.id for t, _, _ in front_topics(session, n, load_clustering_params(), load_front_params(), now)[0]]  # noqa: E731
    first, second = ids(10), ids(20)
    assert second[:10] == first
    assert len(set(second)) == len(second) == 20


def test_front_support_comes_only_from_votes_of_accounts(client, session):
    a, b = make_sources(session, "A", "B")
    make_topic(session, "Sans vote", [a, b], hours_ago=30)  # old and no votes: no front page
    session.commit()
    assert front(client) == []


def test_front_uses_a_constant_number_of_queries(client, world, session):
    from sqlalchemy import event

    from app.db import get_engine

    statements = []
    engine = get_engine()
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        client.get("/api/topics/front")
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(statements) <= 4

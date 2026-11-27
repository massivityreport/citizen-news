"""aggregate(): scores, ranking, ties, cut, publication data. It writes nothing."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, func, select

from app.db import get_engine
from app.models.entities import Edition, EditionTopic, Selection
from app.services import une
from app.services.aggregation import aggregate
from tests.helpers import make_accounts, make_article, make_sources, make_topic, put_une

NOW = datetime(2026, 11, 27, 16, 30, tzinfo=UTC)  # after the closing (16:00 UTC in winter)
DAY = date(2026, 11, 27)


@pytest.fixture
def media(session):
    return make_sources(session, "A", "B", "C", "D")


def topic(session, media, title="T", n=2, hours_ago=1.0, **kw):
    return make_topic(session, title, media[:n], hours_ago=hours_ago, now=NOW, **kw)


def unes(session, wanted: dict[int, int], accounts: int | None = None, day=DAY):
    """`wanted`: topic id -> number of accounts having it (the first accounts of the list)."""
    accounts_ids = make_accounts(session, accounts or max(wanted.values(), default=0))
    for topic_id, score in wanted.items():
        for account in accounts_ids[:score]:
            put_une(session, account, day, [topic_id])
    session.commit()
    return accounts_ids


def ids(rows):
    return [r.topic_id for r in rows]


def test_scores_and_order(session, media):
    a, b, c = (topic(session, media, t) for t in "ABC")
    unes(session, {a.id: 1, b.id: 3, c.id: 2})
    r = aggregate(session, DAY, NOW)
    assert ids(r.ranking) == [b.id, c.id, a.id]
    assert [(t.rank, t.score) for t in r.ranking] == [(1, 3), (2, 2), (3, 1)]
    assert r.participants == 3 and r.ties == []
    assert all(t.broken_by is None and t.tied_with == [] for t in r.ranking)


def test_proportion_of_every_topic(session, media):
    a = topic(session, media)
    unes(session, {a.id: 2})
    r = aggregate(session, DAY, NOW)
    assert r.participants == 2 and r.ranking[0].proportion == 1.0


def test_participants_are_accounts_with_a_non_empty_une(session, media):
    a, b = topic(session, media, "A"), topic(session, media, "B")
    first, second, _empty = make_accounts(session, 3)  # the third one never recorded anything
    put_une(session, first, DAY, [a.id, b.id])
    put_une(session, second, DAY, [a.id])
    session.commit()
    r = aggregate(session, DAY, NOW)
    assert r.participants == 2
    assert [(t.topic_id, t.proportion) for t in r.ranking] == [(a.id, 1.0), (b.id, 0.5)]


def test_a_une_emptied_by_the_citizen_is_not_a_participant(session, media):
    a = topic(session, media)
    [acct] = make_accounts(session, 1)
    put_une(session, acct, DAY, [a.id])
    session.commit()
    une.remove_topic(session, acct, a.id, NOW - timedelta(hours=3))  # still open at that time
    assert aggregate(session, DAY, NOW).participants == 0


def test_tie_broken_by_source_count(session, media):
    few, many = topic(session, media, "few", n=2), topic(session, media, "many", n=4)
    unes(session, {few.id: 2, many.id: 2})
    r = aggregate(session, DAY, NOW)
    assert ids(r.ranking) == [many.id, few.id]
    [tie] = r.ties
    assert (tie.approvals, tie.topic_ids, tie.broken_by, tie.crosses_cut) == (2, [many.id, few.id], "source_count", False)
    assert r.ranking[0].tied_with == [few.id] and r.ranking[1].broken_by == "source_count"


def test_tie_broken_by_updated_at_then_id(session, media):
    old = topic(session, media, "old", hours_ago=5)
    recent = topic(session, media, "recent", hours_ago=1)
    unes(session, {old.id: 1, recent.id: 1})
    r = aggregate(session, DAY, NOW)
    assert ids(r.ranking) == [recent.id, old.id] and r.ties[0].broken_by == "updated_at"

    # Same media count and same updated_at: the smaller id wins.
    x, y = topic(session, media, "x", hours_ago=2), topic(session, media, "y", hours_ago=2)
    y.updated_at = x.updated_at
    session.commit()
    unes(session, {x.id: 1, y.id: 1}, day=date(2026, 11, 26))
    r = aggregate(session, date(2026, 11, 26), NOW)
    assert ids(r.ranking) == [x.id, y.id] and r.ties[0].broken_by == "id"


def test_group_of_three_reports_the_deepest_criterion(session, media):
    a = topic(session, media, "a", n=3, hours_ago=1)
    b = topic(session, media, "b", n=2, hours_ago=1)
    c = topic(session, media, "c", n=2, hours_ago=3)
    unes(session, {a.id: 1, b.id: 1, c.id: 1})
    r = aggregate(session, DAY, NOW)
    assert ids(r.ranking) == [a.id, b.id, c.id]
    assert r.ties[0].broken_by == "updated_at"  # a/b by source_count, b/c needed updated_at


def test_tie_crossing_the_cut(session, media):
    ts = [topic(session, media, f"T{i}") for i in range(12)]
    for t in ts:
        t.updated_at = ts[0].updated_at  # identical: only the id orders them
    session.commit()
    unes(session, {t.id: 1 for t in ts})
    r = aggregate(session, DAY, NOW)
    assert ids(r.topics) == [t.id for t in ts[:10]] and ids(r.next) == [t.id for t in ts[10:]]
    [tie] = r.ties
    assert tie.crosses_cut is True and tie.broken_by == "id" and len(tie.topic_ids) == 12


def test_distinct_scores_give_no_tie(session, media):
    ts = [topic(session, media, f"T{i}") for i in range(12)]
    unes(session, {t.id: 12 - i for i, t in enumerate(ts)})  # all distinct scores
    r = aggregate(session, DAY, NOW)
    assert r.ties == [] and len(r.topics) == 10 and len(r.next) == 2


def test_group_just_after_the_cut_does_not_cross(session, media):
    ts = [topic(session, media, f"T{i}", hours_ago=1 + i) for i in range(12)]
    wanted = {t.id: 20 - i for i, t in enumerate(ts[:10])}
    wanted[ts[10].id] = 5
    wanted[ts[11].id] = 5
    unes(session, wanted)
    r = aggregate(session, DAY, NOW)
    [tie] = r.ties
    assert tie.topic_ids == [ts[10].id, ts[11].id] and tie.crosses_cut is False


def test_fewer_than_ten_topics(session, media):
    a, b = topic(session, media, "A"), topic(session, media, "B")
    unes(session, {a.id: 1, b.id: 1})
    r = aggregate(session, DAY, NOW)
    assert len(r.topics) == 2 and r.next == []


def test_zero_participants(session, media):
    topic(session, media)
    session.commit()
    r = aggregate(session, DAY, NOW)
    assert (r.participants, r.ranking, r.topics, r.next, r.ties) == (0, [], [], [], [])


def test_topics_out_of_the_pool_are_excluded_even_when_in_a_une(session, media):
    inside = topic(session, media, "in")
    single = topic(session, media, "one medium", n=1)  # one medium only: never in the pool
    stale = topic(session, media, "stale", hours_ago=40)  # older than 24 h
    unes(session, {inside.id: 1, single.id: 3, stale.id: 2})
    r = aggregate(session, DAY, NOW)
    assert ids(r.ranking) == [inside.id]
    assert r.participants == 3  # the unes still count as participants


def test_topic_that_left_the_pool_after_a_put_replacement(session, media):
    """PUT replaces the une with existing topics even out of the pool; the closing then counts them for nothing."""
    inside, single = topic(session, media, "in"), topic(session, media, "one medium", n=1)
    [acct] = make_accounts(session, 1)
    session.commit()
    une.replace(session, acct, [single.id, inside.id], NOW - timedelta(hours=3))
    r = aggregate(session, DAY, NOW)
    assert ids(r.ranking) == [inside.id] and r.participants == 1


def test_selections_of_other_days_are_ignored(session, media):
    a = topic(session, media)
    unes(session, {a.id: 2}, day=date(2026, 11, 26))
    assert aggregate(session, DAY, NOW).participants == 0


def test_captures_the_publication_data(session, media):
    t = topic(session, media, "Sujet", n=3)
    make_article(session, media[0], "img", "Autre", hours_ago=0.5, now=NOW, topic_id=t.id, image_url="https://img.example/x.jpg")
    unes(session, {t.id: 1})
    [item] = aggregate(session, DAY, NOW).ranking
    assert (item.title, item.summary) == ("Sujet", "Résumé de Sujet")
    assert (item.source_count, item.article_count, item.image_url) == (3, 4, "https://img.example/x.jpg")
    assert {s["name"] for s in item.sources} == {"A", "B", "C"}
    assert set(item.sources[0]) == {"name", "url", "title", "published_at"}
    assert item.sources[0]["published_at"].endswith("Z")


def test_top_and_extra_are_parameters(session, media):
    ts = [topic(session, media, f"T{i}") for i in range(6)]
    unes(session, {t.id: 6 - i for i, t in enumerate(ts)})
    r = aggregate(session, DAY, NOW, top=2, extra=3)
    assert len(r.topics) == 2 and len(r.next) == 3 and len(r.ranking) == 6


def test_writes_nothing(session, media):
    a = topic(session, media)
    unes(session, {a.id: 1})
    aggregate(session, DAY, NOW)
    assert not session.new and not session.dirty and not session.deleted
    assert session.scalar(select(func.count()).select_from(Edition)) == 0
    assert session.scalar(select(func.count()).select_from(EditionTopic)) == 0


def _count_queries(session, media, n_topics):
    ts = [topic(session, media, f"T{n_topics}-{i}") for i in range(n_topics)]
    unes(session, {t.id: 2 for t in ts}, accounts=2)
    statements = []

    def count(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(get_engine(), "before_cursor_execute", count)
    try:
        aggregate(session, DAY, NOW)
    finally:
        event.remove(get_engine(), "before_cursor_execute", count)
    return len(statements)


def test_number_of_queries_does_not_depend_on_topics(session, media):
    few = _count_queries(session, media, 2)
    session.execute(Selection.__table__.delete())
    many = _count_queries(session, media, 15)
    assert few == many

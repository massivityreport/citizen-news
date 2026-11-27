"""Back office: home statistics (24 h window, totals, 30-day series)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import Account, Article, Topic
from app.services.admin_stats import stats
from tests.helpers import make_sources
from tests.test_admin_articles import count_queries
from tests.test_admin_auth import PASSWORD

URL = "/api/admin/stats"
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=UTC)


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


@pytest.fixture
def source(session):
    return make_sources(session, "A")[0]


def article(session, source, n, when):
    session.add(Article(source_id=source.id, url=f"https://a.example/{n}", title=f"T{n}", fetched_at=when))
    session.flush()


def day(s, date):
    return next(d for d in s.series if d.date == date)


# --- access ----------------------------------------------------------------

def test_401_without_session(client):
    assert client.get(URL).status_code == 401


def test_401_with_citizen_session(logged):
    assert logged.get(URL).status_code == 401


# --- values ----------------------------------------------------------------

def test_empty_database(admin, monkeypatch):
    from app.deps import clock

    admin.app.dependency_overrides[clock] = lambda: NOW
    today = NOW.date().isoformat()
    r = admin.get(URL)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    zero = {"articles": 0, "participants": 0, "selections": 0}
    assert body["last_24h"] == zero and body["total"] == zero
    assert len(body["series"]) == 30
    assert all(p["articles"] == 0 for p in body["series"])
    assert body["series"][-1]["date"] == today


def test_series_is_30_consecutive_utc_days_ending_today(session):
    s = stats(session, NOW)
    assert [d.date for d in s.series][0] == "2026-10-29" and s.series[-1].date == "2026-11-27"
    assert len(s.series) == 30


def test_24h_window_edges(session, source):
    article(session, source, 1, NOW - timedelta(hours=23, minutes=59))  # in
    article(session, source, 2, NOW - timedelta(hours=24, minutes=1))  # out
    article(session, source, 3, NOW - timedelta(hours=24))  # edge: included
    article(session, source, 4, NOW)  # edge: included
    s = stats(session, NOW)
    assert s.last_24h.articles == 3
    assert s.total.articles == 4


def test_utc_day_boundary(session, source):
    article(session, source, 1, datetime(2026, 11, 26, 23, 59, tzinfo=UTC))
    article(session, source, 2, datetime(2026, 11, 27, 0, 0, tzinfo=UTC))
    s = stats(session, NOW)
    assert day(s, "2026-11-26").articles == 1 and day(s, "2026-11-27").articles == 1


def test_non_utc_clock_is_read_in_utc(session, source):
    from zoneinfo import ZoneInfo

    article(session, source, 1, datetime(2026, 11, 27, 22, 30, tzinfo=UTC))
    late = datetime(2026, 11, 27, 23, 45, tzinfo=UTC).astimezone(ZoneInfo("Asia/Tokyo"))  # 28 Nov in Tokyo
    s = stats(session, late)
    assert s.series[-1].date == "2026-11-27" and s.series[-1].articles == 1


def test_outside_30_days_counted_in_total_only(session, source):
    article(session, source, 1, datetime(2026, 10, 28, 23, 59, tzinfo=UTC))  # day 31 back
    article(session, source, 2, datetime(2026, 10, 29, 0, 0, tzinfo=UTC))  # first day of the series
    s = stats(session, NOW)
    assert s.total.articles == 2
    assert sum(d.articles for d in s.series) == 1 and s.series[0].articles == 1


def test_later_today_is_in_todays_bar_but_not_in_the_sliding_window(session, source):
    article(session, source, 1, NOW + timedelta(hours=1))
    s = stats(session, NOW)
    assert s.last_24h.articles == 0 and s.total.articles == 1
    assert s.series[-1].articles == 1  # the series covers today as a whole UTC day


# --- route -----------------------------------------------------------------

def test_route_returns_aggregates_and_nothing_personal(admin, session, source):
    article(session, source, 1, datetime.now(UTC) - timedelta(minutes=5))
    session.commit()
    r = admin.get(URL)
    body = r.json()
    assert body["last_24h"] == {"articles": 1, "participants": 0, "selections": 0}
    assert set(body) == {"last_24h", "total", "series"}
    assert all(set(p) == {"date", "articles", "participants", "selections"} for p in body["series"])
    assert list(body["series"][0]) == ["date", "articles", "participants", "selections"]  # contract order
    assert "vote" not in r.text and "@" not in r.text  # no votes/voters of V1


def test_constant_number_of_queries(admin, session, source):
    from app.db import get_engine

    small = len(count_queries(get_engine(), lambda: admin.get(URL)))
    for n in range(40):
        article(session, source, n, datetime.now(UTC) - timedelta(days=n))
    session.commit()
    big = len(count_queries(get_engine(), lambda: admin.get(URL)))
    assert small == big
    assert big <= 5  # 2 aggregates + the admin session check (+ margin)


# --- participants and selections (V2) ---------------------------------------

def selection(session, account, topic, when, day=NOW.date()):
    from app.models import Selection

    session.add(Selection(account_id=account, topic_id=topic, edition_date=day, created_at=when))
    session.flush()


@pytest.fixture
def unes(session):
    from tests.helpers import make_accounts

    t = [Topic(title=f"S{i}") for i in range(3)]
    session.add_all(t)
    session.flush()
    return make_accounts(session, 3), [x.id for x in t]


def test_participants_are_distinct_accounts_selections_are_rows(session, unes):
    (a, b, _empty), (t1, t2, t3) = unes
    selection(session, a, t1, NOW - timedelta(hours=1))
    selection(session, a, t2, NOW - timedelta(hours=2))
    selection(session, b, t1, NOW - timedelta(hours=3))
    # an account with an empty une has no row: not a participant
    s = stats(session, NOW)
    assert (s.total.participants, s.total.selections) == (2, 3)
    assert (s.last_24h.participants, s.last_24h.selections) == (2, 3)
    today = day(s, "2026-11-27")
    assert (today.participants, today.selections) == (2, 3)


def test_24h_window_and_series_of_selections(session, unes):
    (a, b, _), (t1, t2, _) = unes
    selection(session, a, t1, NOW - timedelta(hours=30), day=date(2026, 11, 26))  # out of the window, yesterday
    selection(session, b, t1, NOW - timedelta(hours=23), day=date(2026, 11, 26))  # in
    selection(session, b, t2, NOW - timedelta(hours=23), day=date(2026, 11, 26))
    s = stats(session, NOW)
    assert (s.total.participants, s.total.selections) == (2, 3)
    assert (s.last_24h.participants, s.last_24h.selections) == (1, 2)
    assert (day(s, "2026-11-26").participants, day(s, "2026-11-26").selections) == (2, 3)  # 30 h ago is still the 26th UTC
    assert day(s, "2026-11-27").selections == 0


def test_same_account_on_two_days_counts_once_in_total(session, unes):
    (a, _, _), (t1, _, _) = unes
    selection(session, a, t1, datetime(2026, 11, 25, 10, tzinfo=UTC), day=date(2026, 11, 25))
    selection(session, a, t1, datetime(2026, 11, 26, 10, tzinfo=UTC), day=date(2026, 11, 26))
    s = stats(session, NOW)
    assert (s.total.participants, s.total.selections) == (1, 2)
    assert day(s, "2026-11-25").participants == day(s, "2026-11-26").participants == 1


def test_route_exposes_selections_no_votes_and_constant_queries(admin, session, unes):
    from app.db import get_engine
    from tests.helpers import make_accounts

    admin.app.dependency_overrides[__import__("app.deps", fromlist=["clock"]).clock] = lambda: NOW
    (a, b, _), (t1, t2, _) = unes
    selection(session, a, t1, NOW - timedelta(hours=1))
    session.commit()
    r = admin.get(URL)
    body = r.json()
    assert body["last_24h"] == {"articles": 0, "participants": 1, "selections": 1}
    assert "votes" not in r.text and "voters" not in r.text
    small = len(count_queries(get_engine(), lambda: admin.get(URL)))
    for acc in make_accounts(session, 20):
        selection(session, acc, t1, NOW - timedelta(days=acc % 25))
        selection(session, acc, t2, NOW - timedelta(days=acc % 25))
    session.commit()
    assert len(count_queries(get_engine(), lambda: admin.get(URL))) == small
    assert len(admin.get(URL).json()["series"]) == 30

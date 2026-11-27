"""Back office: home statistics (24 h window, totals, 30-day series)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Account, Article
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
    from app.services import admin_stats

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(admin_stats, "datetime", Frozen)
    today = NOW.date().isoformat()
    r = admin.get(URL)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    zero = {"articles": 0}
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
    assert body["last_24h"] == {"articles": 1}
    assert set(body) == {"last_24h", "total", "series"}
    assert all(set(p) == {"date", "articles"} for p in body["series"])
    assert "vote" not in r.text and "@" not in r.text


def test_constant_number_of_queries(admin, session, source):
    from app.db import get_engine

    small = len(count_queries(get_engine(), lambda: admin.get(URL)))
    for n in range(40):
        article(session, source, n, datetime.now(UTC) - timedelta(days=n))
    session.commit()
    big = len(count_queries(get_engine(), lambda: admin.get(URL)))
    assert small == big
    assert big <= 5  # 2 aggregates + the admin session check (+ margin)

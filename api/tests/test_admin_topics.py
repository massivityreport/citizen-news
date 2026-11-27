"""Back office: topics list, topic detail (status, support, votes, curve), votes list."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models import Account, Article, Topic, Vote
from tests.helpers import add_votes, make_article, make_sources, make_topic
from tests.test_admin_articles import count_queries
from tests.test_admin_auth import PASSWORD

LIST = "/api/admin/topics"
SECRET = "@private-mail.test"


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


def utc_day(offset: int) -> datetime:
    """Noon UTC, `offset` days from today (UTC)."""
    day = datetime.now(UTC).date() + timedelta(days=offset)
    return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)


def vote_at(session, topic, choice, when, n=None):
    account = Account(email=f"secret{session.query(Account).count()}{SECRET}")
    session.add(account)
    session.flush()
    session.add(Vote(account_id=account.id, topic_id=topic.id, choice=choice, created_at=when))
    session.flush()
    return account


# --- access ----------------------------------------------------------------

ROUTES = [LIST, f"{LIST}/1", f"{LIST}/1/votes"]


@pytest.mark.parametrize("url", ROUTES)
def test_401_without_session(client, url):
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", ROUTES)
def test_401_with_citizen_session(logged, url):
    assert logged.get(url).status_code == 401


# --- list ------------------------------------------------------------------

@pytest.fixture
def listing(session):
    s1, s2, s3 = make_sources(session, "A", "B", "C")
    big = make_topic(session, "Beta", [s1, s2, s3], state="emerged", wave=3, state_changed_at=utc_day(-2))
    make_article(session, s1, "extra", "Deuxième article de A", hours_ago=0.5, topic_id=big.id, image_url="https://img.example/new.jpg")
    make_article(session, s2, "old", "Vieux", hours_ago=30, topic_id=big.id, image_url="https://img.example/old.jpg")
    small = make_topic(session, "alpha", [s1], state="active", wave=1, state_changed_at=utc_day(-1))
    bare = make_topic(session, "Gamma", [], state="reserve", wave=1)
    add_votes(session, big, more=3, not_priority=1, unknown=1)
    add_votes(session, small, more=1)
    session.commit()
    return big.id, small.id, bare.id


def test_aggregates(admin, listing):
    big, small, bare = listing
    items = {i["id"]: i for i in admin.get(LIST).json()["items"]}
    assert items[big] == {
        "id": big, "title": "Beta", "state": "emerged", "wave": 3, "state_changed_at": items[big]["state_changed_at"],
        "article_count": 5, "source_count": 3, "vote_count": 5, "image_url": "https://img.example/new.jpg",
    }
    assert (items[small]["article_count"], items[small]["source_count"], items[small]["vote_count"]) == (1, 1, 1)
    assert items[small]["image_url"] is None
    assert (items[bare]["article_count"], items[bare]["source_count"], items[bare]["vote_count"]) == (0, 0, 0)  # no article, no vote


@pytest.mark.parametrize("sort, order, expected", [
    ("votes", "desc", ["Beta", "alpha", "Gamma"]),
    ("votes", "asc", ["Gamma", "alpha", "Beta"]),
    ("articles", "desc", ["Beta", "alpha", "Gamma"]),
    ("articles", "asc", ["Gamma", "alpha", "Beta"]),
    ("title", "asc", ["alpha", "Beta", "Gamma"]),  # case-insensitive
    ("title", "desc", ["Gamma", "Beta", "alpha"]),
    ("state", "asc", ["alpha", "Beta", "Gamma"]),   # new < active < emerged < reserve
    ("state", "desc", ["Gamma", "Beta", "alpha"]),
    ("state_changed", "desc", ["alpha", "Beta", "Gamma"]),  # never changed: last
    ("state_changed", "asc", ["Beta", "alpha", "Gamma"]),
])
def test_sorts(admin, listing, sort, order, expected):
    res = admin.get(LIST, params={"sort": sort, "order": order})
    assert [i["title"] for i in res.json()["items"]] == expected


def test_ties_break_on_id(admin, session):
    make_sources(session, "A")
    for t in "xyz":
        session.add(Topic(title="Même titre"))
    session.commit()
    asc = [i["id"] for i in admin.get(LIST, params={"sort": "title", "order": "asc"}).json()["items"]]
    desc = [i["id"] for i in admin.get(LIST, params={"sort": "title", "order": "desc"}).json()["items"]]
    assert asc == sorted(asc) and desc == sorted(desc, reverse=True)


def test_filter_by_state_and_pagination(admin, listing):
    res = admin.get(LIST, params={"state": "reserve"}).json()
    assert [i["title"] for i in res["items"]] == ["Gamma"] and res["total"] == 1
    page = admin.get(LIST, params={"page": 2, "page_size": 2, "sort": "title", "order": "asc"}).json()
    assert [i["title"] for i in page["items"]] == ["Gamma"] and page["total"] == 3
    assert admin.get(LIST, params={"page": 5}).json()["items"] == []


@pytest.mark.parametrize("params", [
    {"sort": "id"}, {"sort": "votes; DROP TABLE topics"}, {"order": "x"}, {"state": "deleted"},
    {"page": 0}, {"page_size": 201}, {"page_size": 0},
])
def test_list_422(admin, listing, params):
    assert admin.get(LIST, params=params).status_code == 422


def test_list_is_two_queries_whatever_the_number_of_topics(admin, session):
    from app.db import get_engine

    sources = make_sources(session, "A", "B")
    for i in range(12):
        add_votes(session, make_topic(session, f"T{i}", sources), more=1, prefix=f"q{i}-")
    session.commit()
    stmts = count_queries(get_engine(), lambda: admin.get(LIST, params={"page_size": 200}))
    ours = [s for s in stmts if "FROM topics" in s]
    assert len(ours) == 2  # the page (with its aggregates) and the COUNT


# --- detail ----------------------------------------------------------------

def detail(admin, topic_id):
    res = admin.get(f"{LIST}/{topic_id}")
    assert res.status_code == 200, res.text
    return res.json()


def test_404(admin, session):
    assert admin.get(f"{LIST}/999").status_code == 404
    assert admin.get(f"{LIST}/999/votes").status_code == 404
    assert admin.get(f"{LIST}/x").status_code == 422


def test_status_and_totals(admin, session):
    s1, s2 = make_sources(session, "Alpha", "Beta")
    t = make_topic(session, "Un sujet", [s1, s2], state="active", wave=2, state_changed_at=utc_day(-3), evaluated_at=utc_day(-3))
    make_article(session, s1, "second", "Autre article", hours_ago=5, topic_id=t.id)
    add_votes(session, t, more=6, not_priority=2, unknown=3)
    session.commit()
    d = detail(admin, t.id)
    assert (d["state"], d["wave"], d["article_count"], d["source_count"]) == ("active", 2, 3, 2)
    assert d["state_changed_at"].startswith(utc_day(-3).strftime("%Y-%m-%dT12:00:00"))
    assert d["evaluated_at"] is not None
    assert d["votes"]["more"] == 6 and d["votes"]["not_priority"] == 2 and d["votes"]["unknown"] == 3
    assert d["votes"]["total"] == 11 and d["votes"]["voters"] == 11
    # same function as the halving / support: Wilson bound of 6 "more" among 8 opinions
    from app.services.halving import wilson_lower_bound

    assert d["support"] == {"score": pytest.approx(wilson_lower_bound(6, 8)), "level": "medium", "votes_count": 11}
    assert [a["title"] for a in d["articles"]][0].startswith("Un sujet")  # newest first
    assert len(d["articles"]) == 3 and d["articles_truncated"] is False
    assert d["articles"][0]["source"]["name"] in {"Alpha", "Beta"}


def test_topic_without_votes_or_articles(admin, session):
    t = Topic(title="Vide")
    session.add(t)
    session.commit()
    d = detail(admin, t.id)
    assert d["support"] == {"score": 0.0, "level": "low", "votes_count": 0}
    assert d["votes"]["daily"] == [] and d["votes"]["first_vote_at"] is None and d["articles"] == []
    assert d["front"] == {"on_front": False, "reason": None}


def test_daily_curve_fills_empty_days_with_zero(admin, session):
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Courbe", [s1, s2])
    vote_at(session, t, "more", utc_day(-3))
    vote_at(session, t, "more", utc_day(-3))
    vote_at(session, t, "unknown", utc_day(-3))
    vote_at(session, t, "not_priority", utc_day(-1))
    vote_at(session, t, "more", utc_day(0))
    session.commit()
    daily = detail(admin, t.id)["votes"]["daily"]
    today = utc_day(0).date()
    assert [d["date"] for d in daily] == [(today - timedelta(days=k)).isoformat() for k in (3, 2, 1, 0)]
    assert [(d["more"], d["not_priority"], d["unknown"], d["total"]) for d in daily] == [
        (2, 0, 1, 3), (0, 0, 0, 0), (0, 1, 0, 1), (1, 0, 0, 1),
    ]


def test_daily_curve_is_limited_to_30_days_but_totals_are_not(admin, session):
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Ancien", [s1, s2])
    vote_at(session, t, "more", utc_day(-60))
    vote_at(session, t, "more", utc_day(-29))
    vote_at(session, t, "more", utc_day(-30))  # one day too old: outside the window
    session.commit()
    d = detail(admin, t.id)
    daily = d["votes"]["daily"]
    assert len(daily) == 30 and daily[0]["date"] == (utc_day(0).date() - timedelta(days=29)).isoformat()
    assert daily[0]["total"] == 1 and sum(x["total"] for x in daily) == 1
    assert d["votes"]["total"] == 3 and d["votes"]["voters"] == 3


def test_daily_buckets_are_utc_days(admin, session):
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Minuit", [s1, s2])
    day = utc_day(-1).date()
    vote_at(session, t, "more", datetime(day.year, day.month, day.day, 23, 59, 59, tzinfo=UTC))
    vote_at(session, t, "more", datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=UTC))
    vote_at(session, t, "more", datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=UTC) + timedelta(days=1))
    session.commit()
    daily = detail(admin, t.id)["votes"]["daily"]
    assert [(x["date"], x["total"]) for x in daily] == [(day.isoformat(), 2), ((day + timedelta(days=1)).isoformat(), 1)]


def test_front_status_matches_the_front_page(admin, session):
    """on_front and the reason agree with /api/topics/front for every kind of topic."""
    s1, s2, s3 = make_sources(session, "A", "B", "C")
    surging = make_topic(session, "Mobilisé", [s1, s2, s3], state="active", wave=1)
    add_votes(session, surging, more=12)  # recent votes, medium support -> emerging
    calm = make_topic(session, "Neuf", [s1, s2])  # recent, no votes: documented default (emerging)
    mono = make_topic(session, "Un seul média", [s1])  # one medium, no radar reason
    reserve = make_topic(session, "En réserve", [s1, s2, s3], state="reserve")
    old = make_topic(session, "Trop ancien", [s1, s2], hours_ago=24 * 10)
    radar = make_topic(session, "Sous les radars", [s1, s2], hours_ago=20)
    add_votes(session, radar, more=20, hours_ago=15)  # two media, high score, no recent surge
    session.commit()
    front = {i["id"]: i for i in admin.get("/api/topics/front?limit=50").json()["items"]}
    assert {surging.id, calm.id, radar.id} <= set(front)
    assert not {mono.id, reserve.id, old.id} & set(front)
    for t in (surging, calm, mono, reserve, old, radar):
        d = detail(admin, t.id)["front"]
        assert d["on_front"] is (t.id in front), t.title
        assert d["reason"] == (front[t.id]["reason"] if t.id in front else None), t.title
    assert detail(admin, surging.id)["front"]["reason"]["code"] == "emerging"
    assert detail(admin, radar.id)["front"]["reason"]["code"] == "under_the_radar"


def test_detail_query_count_does_not_grow_with_data(admin, session):
    from app.db import get_engine

    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Requêtes", [s1, s2])
    add_votes(session, t, more=2)
    session.commit()
    few = len(count_queries(get_engine(), lambda: admin.get(f"{LIST}/{t.id}")))
    for i in range(15):
        make_article(session, s1, f"more{i}", f"Article {i}", topic_id=t.id)
    add_votes(session, t, more=20, not_priority=5, prefix="w")
    session.commit()
    assert len(count_queries(get_engine(), lambda: admin.get(f"{LIST}/{t.id}"))) == few


def test_articles_of_a_topic_are_capped(admin, session, monkeypatch):
    from app.services import admin_topics

    monkeypatch.setattr(admin_topics, "MAX_TOPIC_ARTICLES", 2)
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Beaucoup", [s1, s2])
    make_article(session, s1, "x", "Encore", topic_id=t.id)
    session.commit()
    d = detail(admin, t.id)
    assert len(d["articles"]) == 2 and d["articles_truncated"] is True and d["article_count"] == 3


# --- votes list ------------------------------------------------------------

def test_votes_are_paginated_newest_first_with_account_numbers(admin, session):
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Votes", [s1, s2])
    accounts = [vote_at(session, t, ["more", "not_priority", "unknown"][i % 3], utc_day(-i)) for i in range(5)]
    session.commit()
    res = admin.get(f"{LIST}/{t.id}/votes", params={"page_size": 2}).json()
    assert res["total"] == 5 and (res["page"], res["page_size"]) == (1, 2)
    assert [v["account_id"] for v in res["items"]] == [accounts[0].id, accounts[1].id]  # newest first
    assert res["items"][0]["choice"] == "more" and res["items"][0]["date"].startswith(utc_day(0).strftime("%Y-%m-%d"))
    assert set(res["items"][0]) == {"date", "choice", "account_id"}
    last = admin.get(f"{LIST}/{t.id}/votes", params={"page_size": 2, "page": 3}).json()
    assert [v["account_id"] for v in last["items"]] == [accounts[4].id]
    assert admin.get(f"{LIST}/{t.id}/votes", params={"page": 9}).json()["items"] == []
    for bad in ({"page": 0}, {"page_size": 201}, {"page_size": 0}):
        assert admin.get(f"{LIST}/{t.id}/votes", params=bad).status_code == 422


def test_votes_with_the_same_date_keep_a_stable_order(admin, session):
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Égalité", [s1, s2])
    when = utc_day(-1)
    made = [vote_at(session, t, "more", when).id for _ in range(5)]
    session.commit()
    seen = [v["account_id"] for p in (1, 2, 3) for v in admin.get(f"{LIST}/{t.id}/votes", params={"page": p, "page_size": 2}).json()["items"]]
    assert seen == sorted(made, reverse=True)


def test_no_personal_data_in_any_admin_response(admin, session):
    s1, s2 = make_sources(session, "A", "B")
    t = make_topic(session, "Confidentiel", [s1, s2], state="active")
    for i in range(4):
        vote_at(session, t, "more", utc_day(-i))
    add_votes(session, t, more=2, prefix="other", hours_ago=1)
    session.commit()
    bodies = [
        admin.get(url).text
        for url in (
            "/api/admin/articles?page_size=200", "/api/admin/topics?page_size=200", f"/api/admin/topics/{t.id}",
            f"/api/admin/topics/{t.id}/votes?page_size=200", "/api/admin/sources",
        )
    ]
    assert all(bodies)
    emails = [e for (e,) in session.query(Account.email)]
    assert len(emails) == 6
    for body in bodies:
        for email in emails:
            assert email not in body
        assert "private-mail" not in body and "@example.org" not in body
        assert "email" not in body.lower() and "token" not in body.lower() and "hash" not in body.lower()

"""Back-office sources: list, add (with SSRF guard), deactivate/reactivate, delete for good."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Article, DeletedSource, MediaSource, Topic
from app.routers.admin import get_fetcher
from app.services.ingest import ingest, sync_sources
from app.services.safe_fetch import GENERIC_MESSAGE, FetchError, fetch_public
from config.feeds import FeedConfig
from tests.helpers import make_article, make_sources, make_topic, original_url
from tests.test_admin_auth import PASSWORD

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Un article</title><link>https://new.example/a</link></item></channel></rss>"""
EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title></channel></rss>'
SITEMAP = b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'


@pytest.fixture
def admin(client):
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    return client


@pytest.fixture
def fetched(admin):
    """Replace the fetch by a fake: `fetched.body` is what every URL returns; the URLs asked are recorded."""

    class Fake:
        body: bytes | Exception = RSS
        urls: list[str] = []

        def __call__(self, url):
            self.urls.append(url)
            if isinstance(self.body, Exception):
                raise self.body
            return self.body

    fake = Fake()
    fake.urls = []
    admin.app.dependency_overrides[get_fetcher] = lambda: fake
    return fake


def add(admin, name="Nouveau", url="https://new.example/rss"):
    return admin.post("/api/admin/sources", json={"name": name, "feed_url": url})


def count(session, model):
    session.expire_all()
    return session.scalar(select(func.count()).select_from(model))


# --- access ----------------------------------------------------------------

ROUTES = [
    ("GET", "/api/admin/sources", None),
    ("GET", "/api/admin/sources/1", None),
    ("POST", "/api/admin/sources", {"name": "X", "feed_url": "https://x.example/rss"}),
    ("POST", "/api/admin/sources/1/deactivate", None),
    ("POST", "/api/admin/sources/1/reactivate", None),
    ("DELETE", "/api/admin/sources/1?confirm=0", None),
]


@pytest.mark.parametrize("method, path, body", ROUTES)
def test_401_without_session(client, session, method, path, body):
    make_sources(session, "A")
    session.commit()
    assert client.request(method, path, json=body).status_code == 401
    assert session.scalar(select(MediaSource.active)) is True and count(session, MediaSource) == 1


@pytest.mark.parametrize("method, path, body", ROUTES)
def test_401_with_a_citizen_session(logged, session, method, path, body):
    make_sources(session, "A")
    session.commit()
    assert logged.request(method, path, json=body).status_code == 401
    assert count(session, MediaSource) == 1


# --- list --------------------------------------------------------------------

def test_list_has_counts_and_last_article_date(admin, session):
    a, b, c = make_sources(session, "Alpha", "beta", "Gamma")
    make_article(session, a, 1, "t1", hours_ago=30)
    make_article(session, a, 2, "t2", hours_ago=2)
    make_article(session, b, 3, "t3", hours_ago=5)
    b.active = False
    session.commit()
    rows = admin.get("/api/admin/sources").json()
    assert [r["name"] for r in rows] == ["Alpha", "beta", "Gamma"]  # case-insensitive order
    by = {r["name"]: r for r in rows}
    assert by["Alpha"]["article_count"] == 2 and by["Alpha"]["active"] is True
    assert by["Alpha"]["last_article_at"].startswith("2026-11-26T10:00")  # published_at of the newest
    assert by["beta"]["article_count"] == 1 and by["beta"]["active"] is False
    assert by["Gamma"]["article_count"] == 0 and by["Gamma"]["last_article_at"] is None
    assert set(by["Alpha"]) == {"id", "name", "feed_url", "active", "article_count", "last_article_at"}


def test_list_is_one_query_whatever_the_number_of_sources(admin, session):
    from sqlalchemy import event

    from app.db import get_engine

    for s in make_sources(session, *[f"S{i}" for i in range(6)]):
        make_article(session, s, 1, "t")
    session.commit()
    statements: list[str] = []
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    event.listen(get_engine(), "before_cursor_execute", listener)
    try:
        assert len(admin.get("/api/admin/sources").json()) == 6
    finally:
        event.remove(get_engine(), "before_cursor_execute", listener)
    assert len([s for s in statements if "media_sources" in s]) == 1


def test_last_article_date_falls_back_to_fetch_date(admin, session):
    (a,) = make_sources(session, "A")
    session.add(Article(source_id=a.id, url="https://a.example/x", title="t", published_at=None))
    session.commit()
    assert admin.get("/api/admin/sources").json()[0]["last_article_at"] is not None


def test_get_one_and_404(admin, session):
    (a,) = make_sources(session, "A")
    make_article(session, a, 1, "t")
    session.commit()
    assert admin.get(f"/api/admin/sources/{a.id}").json()["article_count"] == 1
    assert admin.get("/api/admin/sources/999").status_code == 404


# --- add ---------------------------------------------------------------------

def test_add_a_valid_source(admin, session, fetched):
    r = add(admin, "  Le   Nouveau  ", "HTTPS://New.Example/rss#frag")
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Le Nouveau" and body["feed_url"] == "https://new.example/rss"
    assert body["active"] is True and body["article_count"] == 0 and body["last_article_at"] is None
    assert fetched.urls == ["https://new.example/rss"]
    assert count(session, MediaSource) == 1


def test_added_source_is_ingested(admin, session, fetched):
    add(admin)
    seen = []
    client = httpx.Client(transport=httpx.MockTransport(lambda r: (seen.append(original_url(r)), httpx.Response(200, content=RSS))[1]))
    ingest(session, [], client=client)
    assert seen == ["https://new.example/rss"] and count(session, Article) == 1


@pytest.mark.parametrize(
    "name, url, message",
    [
        ("A", "ftp://x.example/rss", "http://"),
        ("A", "javascript:alert(1)", "http://"),
        ("A", "file:///etc/passwd", "http://"),
        ("A", "//x.example/rss", "http://"),
        ("A", "x.example/rss", "http://"),
        ("A", "https://user:pw@x.example/rss", "identifiants"),
        ("A", "https://user@x.example/rss", "identifiants"),
        ("A", "https://x.example/rss " + "a" * 5, "interdits"),
        ("A", "https://x.example/" + "a" * 2048, "2048"),
        ("A", "https://x.example:99999/rss", "valide"),
        ("A", "", "obligatoire"),
        ("", "https://x.example/rss", "nom"),
        ("   \t ", "https://x.example/rss", "nom"),
        ("n" * 101, "https://x.example/rss", "100"),
    ],
)
def test_invalid_input_is_refused_in_french_and_nothing_is_fetched(admin, session, fetched, name, url, message):
    r = add(admin, name, url)
    assert r.status_code == 422 and message in r.json()["detail"]
    assert fetched.urls == [] and count(session, MediaSource) == 0


def test_name_of_100_characters_is_accepted(admin, fetched):
    assert add(admin, "n" * 100).status_code == 201


def test_missing_fields_and_huge_values_are_422(admin, fetched):
    assert admin.post("/api/admin/sources", json={"name": "A"}).status_code == 422
    assert add(admin, "A", "https://x.example/" + "a" * 6000).status_code == 422
    assert fetched.urls == []


def test_duplicate_is_409_even_when_deactivated_and_nothing_is_fetched(admin, session, fetched):
    (a,) = make_sources(session, "A")
    a.feed_url = "https://new.example/rss"
    a.active = False
    session.commit()
    r = add(admin, "Autre nom", "https://NEW.example/rss")
    assert r.status_code == 409 and "existe déjà" in r.json()["detail"]
    assert fetched.urls == [] and count(session, MediaSource) == 1


def test_unreadable_feed_is_refused_and_nothing_is_stored(admin, session, fetched):
    for body, text in [
        (b"<html><body>pas un flux", "flux RSS ou Atom"),
        (b"", "aucun article"),
        (EMPTY_RSS, "aucun article"),
        (SITEMAP, "aucun article"),
    ]:
        fetched.body = body
        r = add(admin)
        assert r.status_code == 422 and text in r.json()["detail"], body
    assert count(session, MediaSource) == 0


def test_forbidden_or_unreachable_give_the_same_generic_message(admin, session, fetched):
    fetched.body = FetchError("adresse non publique : 10.0.0.1")
    forbidden = add(admin)
    fetched.body = FetchError("ConnectError")
    unreachable = add(admin)
    assert forbidden.status_code == unreachable.status_code == 422
    assert forbidden.json() == unreachable.json()
    assert GENERIC_MESSAGE in forbidden.json()["detail"] and "10.0.0.1" not in forbidden.json()["detail"]
    assert count(session, MediaSource) == 0


# --- add, with the real SSRF guard (injected resolver and transport: no network) -----------

@pytest.fixture
def guarded(admin):
    """get_fetcher = the real fetch_public, with a fake DNS and a transport that must never be reached for a forbidden URL."""
    dns = {"news.example": ["93.184.216.34"], "internal.example": ["10.0.0.7"], "meta.example": ["169.254.169.254"]}
    reached: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        reached.append(request)
        if request.headers["host"] == "news.example" and request.url.path == "/hop":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:8000/api/admin/me"})
        return httpx.Response(200, content=RSS)

    def resolve(host, port):
        if host not in dns:
            raise FetchError("résolution impossible")
        return dns[host]

    client = httpx.Client(transport=httpx.MockTransport(handler))
    admin.app.dependency_overrides[get_fetcher] = lambda: (lambda url: fetch_public(url, client=client, resolver=resolve))
    admin.reached = reached
    return admin


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/rss",
        "http://127.0.0.1/rss",
        "http://10.1.2.3/rss",
        "http://192.168.0.1/rss",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/rss",
        "http://[::ffff:127.0.0.1]/rss",
        "http://internal.example/rss",
        "http://meta.example/rss",
        "http://unknown.example/rss",
    ],
)
def test_ssrf_targets_are_refused_with_the_generic_message(guarded, session, url):
    r = add(guarded, url=url)
    assert r.status_code == 422 and GENERIC_MESSAGE in r.json()["detail"]
    assert guarded.reached == [] and count(session, MediaSource) == 0
    assert r.json()["detail"] == f"{GENERIC_MESSAGE} Vérifiez l’adresse du flux."  # same text for every refusal, no address


def test_public_to_private_redirect_is_refused(guarded, session):
    r = add(guarded, url="http://news.example/hop")
    assert r.status_code == 422 and GENERIC_MESSAGE in r.json()["detail"]
    assert len(guarded.reached) == 1 and count(session, MediaSource) == 0


def test_public_url_goes_through_the_guard(guarded, session):
    assert add(guarded, url="https://news.example/rss").status_code == 201
    assert guarded.reached[0].url.host == "93.184.216.34"  # pinned to the validated address


# --- deactivate / reactivate -----------------------------------------------------

def test_deactivate_keeps_articles_and_topics_and_reactivate(admin, session):
    a, b = make_sources(session, "A", "B")
    topic = make_topic(session, "Sujet partagé", [a, b])
    session.commit()
    r = admin.post(f"/api/admin/sources/{a.id}/deactivate")
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["article_count"] == 1
    assert admin.post(f"/api/admin/sources/{a.id}/deactivate").json()["active"] is False  # idempotent
    assert count(session, Article) == 2
    assert session.scalar(select(Article.topic_id).where(Article.source_id == a.id)) == topic.id
    r = admin.post(f"/api/admin/sources/{a.id}/reactivate")
    assert r.json()["active"] is True
    assert admin.post(f"/api/admin/sources/{a.id}/reactivate").json()["active"] is True  # idempotent


@pytest.mark.parametrize("action", ["deactivate", "reactivate"])
def test_unknown_source_is_404(admin, action):
    assert admin.post(f"/api/admin/sources/999/{action}").status_code == 404


def test_inactive_source_articles_still_count_for_the_front_and_the_cards(admin, session):
    """Wanted: history is kept. A deactivated source's articles keep their topics eligible and visible."""
    from app.services.topics import eligible_topics
    from config.clustering import load_clustering_params

    a, b = make_sources(session, "A", "B")
    make_topic(session, "Sujet visible", [a, b])
    session.commit()
    admin.post(f"/api/admin/sources/{a.id}/deactivate")
    session.expire_all()
    assert len(session.scalars(eligible_topics(load_clustering_params())).all()) == 1
    front = admin.get("/api/topics/front").json()
    assert [t["title"] for t in front["items"]] == ["Sujet visible"]
    assert sorted(s["name"] for s in front["items"][0]["sources"]) == ["A", "B"]


def test_clustering_still_groups_with_articles_of_an_inactive_source(admin, session):
    from app.services.clustering import cluster
    from tests.helpers import NOW, RETRAITES

    a, b = make_sources(session, "A", "B")
    make_article(session, a, 1, *RETRAITES[0])
    make_article(session, b, 2, *RETRAITES[1])
    a.active = False
    session.commit()
    cluster(session, now=NOW)
    session.expire_all()
    assert count(session, Topic) == 1 and not session.scalars(select(Article.topic_id).where(Article.topic_id.is_(None))).all()


# --- delete for good ---------------------------------------------------------------

def test_delete_with_wrong_confirmation_is_refused(admin, session):
    a, b = make_sources(session, "A", "B")
    make_article(session, a, 1, "t1")
    make_article(session, a, 2, "t2")
    session.commit()
    for wrong in (0, 1, 3):
        r = admin.delete(f"/api/admin/sources/{a.id}?confirm={wrong}")
        assert r.status_code == 409 and "2 articles" in r.json()["detail"]
    assert admin.delete(f"/api/admin/sources/{a.id}").status_code == 422  # confirmation is mandatory
    assert admin.delete(f"/api/admin/sources/{a.id}?confirm=-1").status_code == 422
    assert admin.delete(f"/api/admin/sources/{a.id}?confirm=deux").status_code == 422
    assert count(session, MediaSource) == 2 and count(session, Article) == 2 and count(session, DeletedSource) == 0


def test_delete_with_right_confirmation_removes_source_and_articles(admin, session):
    a, b = make_sources(session, "A", "B")
    make_article(session, a, 1, "t1")
    make_article(session, a, 2, "t2")
    make_article(session, b, 3, "t3")
    session.commit()
    a_id, a_url = a.id, a.feed_url
    r = admin.delete(f"/api/admin/sources/{a.id}?confirm=2")
    assert r.status_code == 200 and r.json() == {"id": a_id, "deleted_articles": 2}
    assert [s.name for s in session.scalars(select(MediaSource))] == ["B"] and count(session, Article) == 1
    assert session.scalars(select(DeletedSource.feed_url)).all() == [a_url]
    assert admin.get(f"/api/admin/sources/{a_id}").status_code == 404
    assert admin.delete(f"/api/admin/sources/{a_id}?confirm=0").status_code == 404


def test_delete_source_without_articles_needs_confirm_zero(admin, session):
    (a,) = make_sources(session, "A")
    session.commit()
    assert admin.delete(f"/api/admin/sources/{a.id}?confirm=1").status_code == 409
    assert admin.delete(f"/api/admin/sources/{a.id}?confirm=0").json()["deleted_articles"] == 0


def test_seed_does_not_recreate_a_deleted_source(admin, session):
    (a,) = make_sources(session, "A")
    make_article(session, a, 1, "t")
    url = a.feed_url
    session.commit()
    admin.delete(f"/api/admin/sources/{a.id}?confirm=1")
    sync_sources(session, [FeedConfig(name="A", feed_url=url)])
    session.commit()
    assert count(session, MediaSource) == 0
    ingest(session, [FeedConfig(name="A", feed_url=url)], client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=RSS))))
    assert count(session, MediaSource) == 0 and count(session, Article) == 0


def test_adding_a_deleted_url_again_is_allowed_and_forgets_the_deletion(admin, session, fetched):
    (a,) = make_sources(session, "A")
    url = a.feed_url
    session.commit()
    admin.delete(f"/api/admin/sources/{a.id}?confirm=0")
    assert count(session, DeletedSource) == 1
    assert add(admin, "A de retour", url).status_code == 201
    assert count(session, DeletedSource) == 0 and count(session, MediaSource) == 1


def test_topics_losing_their_articles_stay_consistent(admin, session):
    """A topic that loses one of its two media drops out of the front (not enough distinct sources);
    one that loses all its articles is hidden everywhere and keeps its votes. Nothing breaks."""
    from tests.helpers import add_votes

    a, b, c = make_sources(session, "A", "B", "C")
    shared = make_topic(session, "Partagé", [a, b])
    only_a = make_topic(session, "Seulement A", [a])
    other = make_topic(session, "Autre", [b, c])
    add_votes(session, only_a, more=2)
    session.commit()
    assert {t["title"] for t in admin.get("/api/topics/front").json()["items"]} == {"Partagé", "Autre"}
    assert admin.delete(f"/api/admin/sources/{a.id}?confirm=2").status_code == 200
    items = admin.get("/api/topics/front").json()["items"]
    assert {t["title"] for t in items} == {"Autre"}
    session.expire_all()
    assert session.get(Topic, only_a.id) is not None and session.get(Topic, shared.id) is not None  # not orphaned rows
    nxt = admin.get("/api/vote/next?count=10")
    assert nxt.status_code == 200 and only_a.id not in {t["id"] for t in nxt.json()["items"]}

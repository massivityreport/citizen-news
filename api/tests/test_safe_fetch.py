"""SSRF guard of the admin feed fetch. No real network: a MockTransport client and an injected resolver."""

import httpx
import pytest

from app.services.safe_fetch import GENERIC_MESSAGE, FetchError, fetch_public

PUBLIC = "93.184.216.34"


def resolver_for(table: dict[str, list[str]]):
    def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise FetchError("résolution impossible")
        return table[host]

    return resolve


class Recorder:
    """A client whose answers come from `routes` (keyed by the Host header the server was asked for)."""

    def __init__(self, routes):
        self.requests: list[httpx.Request] = []
        self.routes = routes
        self.client = httpx.Client(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes[request.headers["host"] + request.url.path]
        return route(request) if callable(route) else route


DNS = resolver_for({"news.example": [PUBLIC], "other.example": ["93.184.216.35"]})


def get(url, routes=None, resolver=DNS, **kw):
    rec = Recorder(routes or {})
    return fetch_public(url, client=rec.client, resolver=resolver, **kw), rec


def refused(url, routes=None, resolver=DNS, **kw):
    rec = Recorder(routes or {})
    with pytest.raises(FetchError) as info:
        fetch_public(url, client=rec.client, resolver=resolver, **kw)
    assert str(info.value) == GENERIC_MESSAGE
    return rec


def test_public_fetch_connects_to_the_validated_ip_and_keeps_host():
    body, rec = get("https://news.example/rss", {"news.example/rss": httpx.Response(200, content=b"<rss/>")})
    assert body == b"<rss/>"
    request = rec.requests[0]
    assert request.url.host == PUBLIC  # the validated address, not a second DNS lookup
    assert request.headers["host"] == "news.example"
    assert request.extensions["sni_hostname"] == "news.example"


def test_non_default_port_is_kept_in_the_host_header():
    _, rec = get("http://news.example:8080/rss", {"news.example:8080/rss": httpx.Response(200, content=b"x")})
    assert rec.requests[0].url.port == 8080


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/rss",
        "http://LOCALHOST./rss",
        "http://foo.localhost/rss",
        "http://127.0.0.1/rss",
        "http://127.1/rss",
        "http://2130706433/rss",
        "http://0x7f000001/rss",
        "http://10.0.0.5/rss",
        "http://172.16.0.1/rss",
        "http://192.168.1.10/rss",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/rss",
        "http://0.0.0.0/rss",
        "http://224.0.0.1/rss",
        "http://[::1]/rss",
        "http://[::]/rss",
        "http://[fe80::1]/rss",
        "http://[fc00::1]/rss",
        "http://[::ffff:127.0.0.1]/rss",
        "http://[::ffff:10.0.0.1]/rss",
        "http://[::ffff:169.254.169.254]/rss",
        "ftp://news.example/rss",
        "file:///etc/passwd",
        "gopher://news.example/",
        "https://user:pw@news.example/rss",
        "https://news.example@evil.example/rss",
        "http://news.example:0/rss",
        "http:///rss",
        "",
    ],
)
def test_forbidden_urls_are_refused_without_any_request(url):
    assert refused(url).requests == []


def test_dns_name_resolving_to_a_private_address_is_refused():
    dns = resolver_for({"intranet.example": ["10.1.2.3"]})
    assert refused("https://intranet.example/rss", resolver=dns).requests == []


@pytest.mark.parametrize("bad", ["127.0.0.1", "169.254.169.254", "::1", "::ffff:10.0.0.1", "fe80::1%eth0"])
def test_every_resolved_address_is_checked(bad):
    dns = resolver_for({"mixed.example": [PUBLIC, bad]})  # one public answer does not excuse the others
    assert refused("https://mixed.example/rss", resolver=dns).requests == []


def test_unresolvable_and_empty_answers_are_refused():
    assert refused("https://nowhere.example/rss").requests == []
    assert refused("https://empty.example/rss", resolver=resolver_for({"empty.example": []})).requests == []


def test_redirect_to_another_public_host_is_followed_and_pinned_again():
    routes = {
        "news.example/rss": httpx.Response(301, headers={"Location": "https://other.example/new"}),
        "other.example/new": httpx.Response(200, content=b"<rss/>"),
    }
    body, rec = get("https://news.example/rss", routes)
    assert body == b"<rss/>" and [r.url.host for r in rec.requests] == [PUBLIC, "93.184.216.35"]


def test_relative_redirect_is_resolved_against_the_current_url():
    routes = {
        "news.example/rss": httpx.Response(302, headers={"Location": "/feed.xml"}),
        "news.example/feed.xml": httpx.Response(200, content=b"ok"),
    }
    assert get("https://news.example/rss", routes)[0] == b"ok"


@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:8000/api/admin/me",
        "http://[::1]/",
        "http://10.0.0.1/",
        "file:///etc/passwd",
        "ftp://other.example/x",
        "https://user:pw@other.example/x",
    ],
)
def test_redirect_from_public_to_forbidden_is_refused(location):
    routes = {"news.example/rss": httpx.Response(302, headers={"Location": location})}
    assert len(refused("https://news.example/rss", routes).requests) == 1  # only the first hop was requested


def test_redirect_to_a_name_resolving_privately_is_refused():
    dns = resolver_for({"news.example": [PUBLIC], "rebind.example": ["192.168.0.9"]})
    routes = {"news.example/rss": httpx.Response(302, headers={"Location": "https://rebind.example/x"})}
    assert len(refused("https://news.example/rss", routes, resolver=dns).requests) == 1


def test_redirect_loop_is_refused():
    routes = {"news.example/rss": httpx.Response(302, headers={"Location": "https://news.example/rss"})}
    assert len(refused("https://news.example/rss", routes).requests) == 6  # the first hop and 5 redirects


def test_exactly_five_redirects_are_allowed():
    routes = {f"news.example/{i}": httpx.Response(302, headers={"Location": f"/{i + 1}"}) for i in range(5)}
    routes["news.example/5"] = httpx.Response(200, content=b"end")
    assert get("https://news.example/0", routes)[0] == b"end"
    routes["news.example/5"] = httpx.Response(302, headers={"Location": "/6"})
    routes["news.example/6"] = httpx.Response(200, content=b"end")
    refused("https://news.example/0", routes)


def test_http_error_and_transport_error_give_the_same_generic_message():
    refused("https://news.example/rss", {"news.example/rss": httpx.Response(404)})
    refused("https://news.example/rss", {"news.example/rss": httpx.Response(500)})

    def boom(request):
        raise httpx.ConnectError("connection refused to 93.184.216.34")

    refused("https://news.example/rss", {"news.example/rss": boom})


def test_error_message_does_not_leak_the_address():
    rec = Recorder({})
    with pytest.raises(FetchError) as info:
        fetch_public("http://169.254.169.254/", client=rec.client, resolver=DNS)
    assert "169" not in str(info.value) and str(info.value) == GENERIC_MESSAGE


def test_body_size_is_bounded():
    routes = {"news.example/rss": httpx.Response(200, content=b"x" * 101)}
    refused("https://news.example/rss", routes, max_bytes=100)
    assert get("https://news.example/rss", routes, max_bytes=101)[0] == b"x" * 101


def test_overall_deadline(monkeypatch):
    import app.services.safe_fetch as module

    ticks = iter(range(0, 1000, 6))  # each look at the clock is 6 s later: the 10 s budget is gone after two
    monkeypatch.setattr(module, "time", type("T", (), {"monotonic": staticmethod(lambda: next(ticks))}))
    refused("https://news.example/rss", {"news.example/rss": httpx.Response(200, content=b"x")})


def test_own_client_ignores_proxy_environment_and_does_not_follow_redirects(monkeypatch):
    seen = {}

    class Spy(httpx.Client):
        def __init__(self, **kw):
            seen.update(kw)
            super().__init__(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"ok")), **kw)

    import app.services.safe_fetch as module

    monkeypatch.setattr(module.httpx, "Client", Spy)
    assert fetch_public("https://news.example/rss", resolver=DNS) == b"ok"
    assert seen["trust_env"] is False and seen["follow_redirects"] is False

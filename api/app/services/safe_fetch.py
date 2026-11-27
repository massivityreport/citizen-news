"""Fetch a URL typed by an admin without letting the server be used to reach its own network (SSRF).

Rules, applied to the URL AND to every redirect hop (followed by hand, 5 at most):
- http(s) only, no user:pass@, a host that is a plain DNS name or a public IP literal (`public_host`,
  shared with the image validation: no localhost, no private/loopback/link-local/reserved/multicast IP,
  IPv4-mapped IPv6 judged as the IPv4 it wraps);
- the name is resolved ONCE and EVERY returned address must be public; the connection then goes to
  that validated IP (Host header and TLS SNI/certificate check keep the original name), so a DNS answer
  that changes between the check and the connection (DNS rebinding) cannot redirect the request;
- proxies from the environment are ignored (`trust_env=False`): the connection must be the one we validated;
- bounded: 10 s overall, 5 MB of (decoded) body.

Every failure raises FetchError with ONE generic message, whether the target was forbidden, unreachable,
slow or answered with an error: the API must not tell an admin which internal hosts exist.
The cause goes to the log only.

Used by the admin form AND by the periodic ingestion (every feed, feeds.yaml included).

Residual limit: getaddrinfo (system_resolver) has no timeout of its own; the 10 s deadline is only checked
between steps, so a name server that hangs can hold a request longer than that.
"""

import ipaddress
import logging
import socket
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.services.feed_url import MAX_URL_CHARS
from app.services.images import is_public_ip, public_host

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
MAX_BYTES = 5_000_000
MAX_REDIRECTS = 5

USER_AGENT = "CitizenNewsBot/0.1 (RSS reader)"
GENERIC_MESSAGE = "Cette adresse est refusée ou injoignable."

Resolver = Callable[[str, int], list[str]]


class FetchError(Exception):
    """The URL cannot be fetched. `str()` is the generic message; the reason is only logged."""

    def __init__(self, reason: str):
        super().__init__(GENERIC_MESSAGE)
        self.reason = reason


def system_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError(f"résolution impossible ({exc})") from exc
    return sorted({info[4][0] for info in infos})


def check_syntax(url: str) -> tuple[str, str, int]:
    """(scheme, host, port) of an acceptable URL, else FetchError. No network."""
    if len(url) > MAX_URL_CHARS or any(ch.isspace() or ord(ch) < 32 or ch == "\\" for ch in url):
        raise FetchError("URL invalide")
    try:
        parts = urlsplit(url)
        port = parts.port
        hostname = parts.hostname
    except ValueError as exc:
        raise FetchError("URL invalide") from exc
    if parts.scheme not in ("http", "https") or not hostname:
        raise FetchError("schéma ou hôte refusé")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise FetchError("identifiants dans l'URL")
    if port == 0:
        raise FetchError("port invalide")
    host = public_host(hostname)
    if host is None:
        raise FetchError("hôte non public")
    return parts.scheme, host, port or (443 if parts.scheme == "https" else 80)


def _validated_ip(host: str, port: int, resolver: Resolver) -> str:
    """An address of `host`, after checking that ALL its addresses are public."""
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = resolver(host, port)
    if not addresses:
        raise FetchError("aucune adresse")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError as exc:
            raise FetchError("adresse invalide") from exc
        if not is_public_ip(ip):
            raise FetchError("adresse non publique")
    return addresses[0]


def _pinned(url: str, scheme: str, host: str, port: int, ip: str) -> tuple[str, dict[str, str], dict]:
    """The request to send: the URL with the validated IP as host, the original Host header, and the SNI
    name so that the TLS certificate is still checked against the real host name."""
    parts = urlsplit(url)
    default = 443 if scheme == "https" else 80
    ip_host = f"[{ip}]" if ":" in ip else ip
    netloc = ip_host if port == default else f"{ip_host}:{port}"
    pinned = urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))
    host_header = f"[{host}]" if ":" in host else host
    if port != default:
        host_header += f":{port}"
    return pinned, {"Host": host_header}, {"sni_hostname": host}


def fetch_public(
    url: str,
    *,
    client: httpx.Client | None = None,
    resolver: Resolver | None = None,
    max_bytes: int = MAX_BYTES,
    timeout: float = TIMEOUT_SECONDS,
) -> bytes:
    """The body of `url` (after at most 5 validated redirects), or FetchError. `client` and `resolver`
    are injected by the tests: no real network is needed."""
    resolver = resolver or system_resolver
    own_client = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)
    deadline = time.monotonic() + timeout
    current = url.strip()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if time.monotonic() > deadline:
                raise FetchError("délai dépassé")
            body_or_next = _hop(client, current, resolver, max_bytes, deadline)
            if isinstance(body_or_next, bytes):
                return body_or_next
            current = body_or_next[0]
        raise FetchError("trop de redirections")
    except FetchError as exc:
        log.info("fetch refused for %r: %s", url[:200], exc.reason)
        raise
    except (httpx.HTTPError, OSError, ValueError) as exc:
        log.info("fetch failed for %r: %s", url[:200], type(exc).__name__)
        raise FetchError(type(exc).__name__) from exc
    finally:
        if own_client:
            client.close()


def _hop(client: httpx.Client, url: str, resolver: Resolver, max_bytes: int, deadline: float) -> bytes | tuple[str]:
    """One request to a validated address: the body, or (next URL,) when the answer is a redirect."""
    scheme, host, port = check_syntax(url)
    target, headers, extensions = _pinned(url, scheme, host, port, _validated_ip(host, port, resolver))
    headers |= {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "identity",  # no compressed body: the 5 MB cap is then a cap on what is read, not on a gzip bomb
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    }
    with client.stream("GET", target, headers=headers, extensions=extensions, follow_redirects=False) as response:
        if response.is_redirect:
            return (urljoin(url, response.headers["location"].strip()),)
        if response.status_code != 200:
            raise FetchError(f"statut HTTP {response.status_code}")
        body = bytearray()
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > max_bytes:
                raise FetchError("réponse trop volumineuse")
            if time.monotonic() > deadline:
                raise FetchError("délai dépassé")
        return bytes(body)

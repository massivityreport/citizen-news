"""Article images found in feed entries. Hotlink only: we keep a validated URL, never the bytes,
and never make a request to the media. Nothing here raises because of an image."""

import ipaddress
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_IMAGE_URL_CHARS = 500
# A browser (WHATWG) treats "\" as "/", so urlsplit and the browser would disagree on the host;
# a valid URL has percent-encoded quotes and angle brackets.
_FORBIDDEN_URL_CHARS = frozenset('\\"\'<>')
_LABEL_RE = re.compile(r"^[a-z0-9-]{1,63}$")


def _has_forbidden_char(text: str) -> bool:
    return any(
        ch.isspace() or ch in _FORBIDDEN_URL_CHARS or unicodedata.category(ch) in ("Cc", "Cf") for ch in text
    )


def public_host(host: str) -> str | None:
    """The host as stored (lowercase; IDN converted to punycode), or None when it is not a plain public
    DNS name or public IP literal. Local and private targets are refused: the reader's browser would
    request them on the reader's own network."""
    if ":" in host:  # IPv6 literal (urlsplit strips the brackets)
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return None
        return host if is_public_ip(ip) else None
    try:
        host = host.encode("idna").decode("ascii") if not host.isascii() else host
    except UnicodeError:
        return None
    labels = host.split(".")
    if len(host) > 253 or not all(_LABEL_RE.match(label) for label in labels):
        return None
    if host == "localhost" or host.endswith(".localhost"):
        return None
    last = labels[-1]
    if last.isdigit() or last.startswith("0x"):
        # Looks like an IPv4 address (a browser also reads "2130706433" or "0x7f.1" as one): strict dotted quad only.
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return None
        return host if is_public_ip(ip) else None
    return host


def is_public_ip(ip) -> bool:
    if getattr(ip, "ipv4_mapped", None) is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_image_url(raw: object, base: str | None = None) -> str | None:
    """The URL to store, or None. A relative URL is resolved against `base` (the article link).
    Accepted: https only (scheme lowercased), a public host (letters, digits, dots, hyphens, or an
    IP literal that is not private/loopback/link-local/reserved; IDN converted to punycode), valid
    port, no user:pass@, no space, control character, backslash or any of " ' < >, <= 500 chars."""
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate or len(candidate) > MAX_IMAGE_URL_CHARS * 2:
        return None
    # Checked before urljoin, which silently drops tabs and newlines.
    if _has_forbidden_char(candidate):
        return None
    try:
        # an absolute URL is never joined: urljoin would fill an empty host from the base
        url = candidate if urlsplit(candidate).scheme or not base else urljoin(base, candidate)
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            return None
        if "@" in parts.netloc or parts.username is not None or parts.password is not None:
            return None
        port = parts.port  # raises ValueError on a malformed or out-of-range port
        if port == 0:
            return None
        host = public_host(parts.hostname)
        if host is None:
            return None
        netloc = f"[{host}]" if ":" in host else host
        if port is not None:
            netloc += f":{port}"
        url = urlunsplit(("https", netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return None
    if len(url) > MAX_IMAGE_URL_CHARS or _has_forbidden_char(url):
        return None
    return url


class _ImgSrcs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.srcs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            src = dict(attrs).get("src")
            if src:
                self.srcs.append(src)


def _html_img_srcs(html: object) -> list[str]:
    if not html or not isinstance(html, str):
        return []
    parser = _ImgSrcs()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed markup: keep what was found so far
        pass
    return parser.srcs


def _mime(item: dict) -> str:
    return str(item.get("type") or "").lower()


def candidate_image_urls(entry) -> list:
    """Raw candidates in priority order: media:content (image), media:thumbnail, image enclosures,
    then the <img src> of the content / summary HTML."""
    out: list = []
    for item in entry.get("media_content") or []:
        if isinstance(item, dict) and (str(item.get("medium") or "").lower() == "image" or _mime(item).startswith("image/")):
            out.append(item.get("url"))
    for item in entry.get("media_thumbnail") or []:
        if isinstance(item, dict):
            out.append(item.get("url"))
    for item in entry.get("links") or []:
        if isinstance(item, dict) and item.get("rel") == "enclosure" and _mime(item).startswith("image/"):
            out.append(item.get("href"))
    for content in entry.get("content") or []:
        if isinstance(content, dict):
            out.extend(_html_img_srcs(content.get("value")))
    out.extend(_html_img_srcs(entry.get("summary") or entry.get("description")))
    return out


def extract_image_url(entry, base: str | None) -> str | None:
    """First valid image URL of a feedparser entry, or None."""
    try:
        for raw in candidate_image_urls(entry):
            valid = validate_image_url(raw, base)
            if valid:
                return valid
    except Exception:  # an image must never break ingestion
        return None
    return None

"""Article images found in feed entries. Hotlink only: we keep a validated URL, never the bytes,
and never make a request to the media. Nothing here raises because of an image."""

import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

MAX_IMAGE_URL_CHARS = 500


def _has_forbidden_char(text: str) -> bool:
    return any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf") for ch in text)


def validate_image_url(raw: object, base: str | None = None) -> str | None:
    """The URL to store, or None. A relative URL is resolved against `base` (the article link).
    Accepted: https only, non-empty host, no user:pass@, no space or control character, <= 500 chars."""
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
        parts.port  # noqa: B018 - raises ValueError on a malformed port
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

"""One normal form for feed URLs, used wherever they are stored or compared (admin form, feeds.yaml
seeding, deleted_sources), so that `https://News.Example/rss` and `https://news.example/rss#x` are the same source."""

import re
from urllib.parse import urlsplit, urlunsplit

MAX_URL_CHARS = 2048


class FeedUrlError(ValueError):
    """The URL is refused; the message is French and can be shown to the admin."""


def normalize_feed_url(raw: str) -> str:
    """http(s) only, no user:pass@, scheme and host lowercased, no fragment, 2048 characters at most."""
    url = raw.strip()
    if not url:
        raise FeedUrlError("L’adresse du flux est obligatoire.")
    if len(url) > MAX_URL_CHARS:
        raise FeedUrlError(f"L’adresse du flux ne doit pas dépasser {MAX_URL_CHARS} caractères.")
    if re.search(r"[\s\\\x00-\x1f]", url):
        raise FeedUrlError("L’adresse du flux contient des caractères interdits (espace, retour à la ligne, barre oblique inverse).")
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018  (raises ValueError on a malformed port)
    except ValueError:
        raise FeedUrlError("L’adresse du flux n’est pas valide.") from None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise FeedUrlError("L’adresse du flux doit commencer par http:// ou https://.")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise FeedUrlError("L’adresse du flux ne doit pas contenir d’identifiants (utilisateur:motdepasse@).")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))

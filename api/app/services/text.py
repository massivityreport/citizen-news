"""Text helpers: HTML cleaning, accent folding and clean truncation."""

import re
import unicodedata
from html import unescape
from html.parser import HTMLParser

_SKIPPED_TAGS = {"script", "style"}
_BLOCK_TAGS = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
_SPACES = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIPPED_TAGS:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIPPED_TAGS and self._skip:
            self._skip -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def clean_html(value: str | None) -> str:
    """Strip tags and entities from a feed field and collapse whitespace."""
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    text = unescape("".join(parser.parts))
    return _SPACES.sub(" ", text.replace("\xa0", " ")).strip()


def fold(value: str) -> str:
    """Lowercase and strip accents (« Élysée » -> « elysee »)."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def truncate(value: str, limit: int) -> str:
    """Truncate at a word boundary, adding an ellipsis; text within the limit is returned as is."""
    if len(value) <= limit:
        return value
    cut = value[: limit - 1]
    if value[limit - 1] != " " and " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.!?-–—") + "…"

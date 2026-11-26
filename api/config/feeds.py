"""Typed, validated loader for config/feeds.yaml."""

from pathlib import Path
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_PATH = Path(__file__).with_name("feeds.yaml")


class FeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    feed_url: str

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("feed_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        value = value.strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("feed_url must be a valid http(s) URL")
        return value


class FeedsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feeds: list[FeedConfig] = []

    @model_validator(mode="after")
    def _no_duplicates(self):
        for attr in ("name", "feed_url"):
            seen: set[str] = set()
            for feed in self.feeds:
                key = getattr(feed, attr).casefold()
                if key in seen:
                    raise ValueError(f"duplicate {attr}: {getattr(feed, attr)}")
                seen.add(key)
        return self


def load_feeds(path: Path | str = DEFAULT_PATH) -> list[FeedConfig]:
    """Load and validate the feed list; raises pydantic.ValidationError on invalid content."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return list(FeedsConfig.model_validate(data).feeds)

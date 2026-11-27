"""HTTP response models (see docs/api-contract.md)."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    name: str
    url: str
    title: str
    published_at: datetime | None


class TopicCard(BaseModel):
    id: int
    title: str
    summary: str
    sources: list[SourceOut]
    article_count: int
    source_count: int
    first_seen_at: datetime
    updated_at: datetime
    image_url: str | None


class PoolOut(BaseModel):
    edition_date: date
    closes_at: datetime
    open: bool
    total: int  # topics of the tab (items is capped at 300)
    items: list[TopicCard]


class UneOut(BaseModel):
    edition_date: date
    closes_at: datetime
    open: bool
    topic_ids: list[int]


class MergeOut(BaseModel):
    added: int
    ignored: int
    une: UneOut


# --- Authentication ---

import re
from typing import Annotated

from pydantic import field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


TopicId = Annotated[int, Field(gt=0, le=2_147_483_647)]


class TopicIds(BaseModel):
    """A list of topic ids typed by a citizen: positive integers, deduplicated (order kept), at most 10 once
    deduplicated (the raw length is capped too, to protect the parser)."""

    topic_ids: list[TopicId] = Field(max_length=100)

    @field_validator("topic_ids")
    @classmethod
    def _dedupe(cls, value: list[int]) -> list[int]:
        value = list(dict.fromkeys(value))
        if len(value) > 10:
            raise ValueError("10 sujets au plus")
        return value


class MagicLinkRequest(BaseModel):
    email: str
    draft: TopicIds | None = None  # the une typed before logging in; merged by /auth/verify

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        email = value.strip().lower()
        if len(email) > 254 or not _EMAIL_RE.match(email):
            raise ValueError("adresse e-mail invalide")
        return email


class VerifyRequest(BaseModel):
    token: str


class EmailOut(BaseModel):
    email: str


class DraftResult(BaseModel):
    added: int
    ignored: int


class VerifyOut(BaseModel):
    email: str
    draft: DraftResult | None


class AdminLoginRequest(BaseModel):
    password: str = Field(max_length=1024)


# --- Back office: sources ---

class AdminSourceCreate(BaseModel):
    # Loose limits here (protect the parser): the precise rules, with their French messages, are in services/sources.py.
    name: str = Field(max_length=1000)
    feed_url: str = Field(max_length=5000)


class AdminSourceOut(BaseModel):
    id: int
    name: str
    feed_url: str
    active: bool
    article_count: int
    last_article_at: datetime | None


class AdminSourceDeleted(BaseModel):
    id: int
    deleted_articles: int


# --- Back office: articles, topics (read only; never any personal data) ---


class AdminSourceRef(BaseModel):
    id: int
    name: str
    active: bool


class AdminTopicRef(BaseModel):
    id: int
    title: str


class AdminArticleOut(BaseModel):
    id: int
    title: str
    url: str
    source: AdminSourceRef
    published_at: datetime | None
    fetched_at: datetime
    topic: AdminTopicRef | None
    grouped: bool


class AdminArticlePage(BaseModel):
    items: list[AdminArticleOut]
    total: int
    page: int
    page_size: int


class AdminTopicRow(BaseModel):
    id: int
    title: str
    updated_at: datetime
    article_count: int
    source_count: int
    image_url: str | None


class AdminTopicPage(BaseModel):
    items: list[AdminTopicRow]
    total: int
    page: int
    page_size: int


class AdminStatsCounts(BaseModel):
    articles: int


class AdminStatsDay(BaseModel):
    date: str  # YYYY-MM-DD, UTC
    articles: int


class AdminStats(BaseModel):
    last_24h: AdminStatsCounts
    total: AdminStatsCounts
    series: list[AdminStatsDay]


class AdminTopicArticle(BaseModel):
    id: int
    title: str
    url: str
    source: AdminSourceRef
    published_at: datetime | None


class AdminTopicDetail(BaseModel):
    id: int
    title: str
    summary: str
    first_seen_at: datetime
    updated_at: datetime
    article_count: int
    source_count: int
    articles: list[AdminTopicArticle]
    articles_truncated: bool

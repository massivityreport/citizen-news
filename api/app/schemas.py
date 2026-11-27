"""HTTP response models (see docs/api-contract.md)."""

from datetime import datetime

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


# --- Authentication ---

import re

from pydantic import field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


class MagicLinkRequest(BaseModel):
    email: str

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

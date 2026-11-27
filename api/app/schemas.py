"""HTTP response models (see docs/api-contract.md)."""

from datetime import date, datetime
from typing import Literal

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

from pydantic import ConfigDict, field_validator, model_validator

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


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise ValueError("adresse e-mail invalide")
    return email


class MagicLinkRequest(BaseModel):
    email: str
    draft: TopicIds | None = None  # the une typed before logging in; merged by /auth/verify

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return normalize_email(value)


FEEDBACK_MAX_LENGTH = 2000
FEEDBACK_MAX_ACTIONS = 20


def _clean_line(value: str) -> str:
    value = value.strip()
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("valeur invalide")
    return value


class RecentAction(BaseModel):
    """One step of the visitor's recent journey: a page opened, a topic added to / removed from the front page, a login."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["page", "topic_added", "topic_removed", "login"]
    at: str = Field(max_length=40)
    page: str | None = Field(None, max_length=500)
    topic_id: int | None = Field(None, ge=1, le=2**31 - 1)

    @field_validator("at", "page")
    @classmethod
    def _line(cls, value: str | None) -> str | None:
        return None if value is None else _clean_line(value)

    @model_validator(mode="after")
    def _fields_match_type(self) -> "RecentAction":
        if (self.type == "page") != (self.page is not None):
            raise ValueError("page attendue pour une page, interdite sinon")
        if (self.type in ("topic_added", "topic_removed")) != (self.topic_id is not None):
            raise ValueError("topic_id attendu pour un sujet, interdit sinon")
        return self


class FeedbackRequest(BaseModel):
    """An opinion typed on the site. `email` is only read for visitors without a session."""

    kind: Literal["problem", "idea", "other"]
    message: str = Field(max_length=FEEDBACK_MAX_LENGTH * 2)  # raw cap protects the parser; the real one applies after strip
    email: str | None = Field(None, max_length=400)
    page_name: str = Field(max_length=200)
    page_url: str = Field(max_length=500)
    screen: str = Field(pattern=r"^\d{1,4}x\d{1,4}$")
    recent_actions: list[RecentAction] | None = Field(None, max_length=FEEDBACK_MAX_ACTIONS)  # sent only if the visitor ticked the box

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > FEEDBACK_MAX_LENGTH:
            raise ValueError("message invalide")
        return value

    @field_validator("page_name", "page_url")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("valeur invalide")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return None if value is None else normalize_email(value)


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
    article_count: int
    source_count: int
    updated_at: datetime
    approvals: int  # accounts that have the topic in their une of the edition in progress
    image_url: str | None


class AdminTopicPage(BaseModel):
    items: list[AdminTopicRow]
    total: int
    page: int
    page_size: int


class AdminStatsCounts(BaseModel):
    articles: int
    participants: int  # distinct accounts with at least one selection
    selections: int  # selection rows (topics put in a une)


class AdminStatsDay(BaseModel):
    date: str  # YYYY-MM-DD, UTC (first key, as in the contract)
    articles: int
    participants: int
    selections: int


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


class AdminTopicHistory(BaseModel):
    edition_date: date
    rank: int | None  # None: had approvals but did not make the published une
    approvals: int
    proportion: float


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
    approvals: int
    history: list[AdminTopicHistory]


# --- Published editions (public) ---


class EditionTopicOut(BaseModel):
    rank: int
    topic_id: int | None  # None once the live topic was deleted
    title: str
    summary: str
    sources: list[SourceOut]
    source_count: int
    article_count: int
    approvals: int
    proportion: float  # approvals / participants, rounded to 3 decimals
    image_url: str | None


class EditionOut(BaseModel):
    date: date
    published_at: datetime
    participants: int
    topics: list[EditionTopicOut]


class CurrentEditionOut(BaseModel):
    edition: EditionOut | None
    next_close_at: datetime
    server_time: datetime


class EditionSummary(BaseModel):
    date: date
    published_at: datetime
    participants: int
    topic_count: int


class EditionList(BaseModel):
    items: list[EditionSummary]


# --- Admin: editions ---


class AdminEditionPage(BaseModel):
    items: list[EditionSummary]
    total: int
    page: int
    page_size: int


class AdminItem(BaseModel):
    rank: int
    topic_id: int
    title: str
    approvals: int
    proportion: float
    source_count: int
    article_count: int
    updated_at: datetime
    tied_with: list[int]
    broken_by: Literal["source_count", "updated_at", "id"] | None


class AdminTie(BaseModel):
    approvals: int
    topic_ids: list[int]
    broken_by: Literal["source_count", "updated_at", "id"]
    crosses_cut: bool


class AdminPreview(BaseModel):
    computed_at: datetime
    edition_date: date
    participants: int
    topics: list[AdminItem]
    next: list[AdminItem]
    ties: list[AdminTie]

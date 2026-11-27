"""HTTP response models (see docs/api-contract.md)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    name: str
    url: str
    title: str
    published_at: datetime | None


class SupportOut(BaseModel):
    level: Literal["low", "medium", "high"]
    votes_count: int


class ReasonOut(BaseModel):
    code: Literal["common_priority", "strong_mobilisation", "under_the_radar", "emerging"]
    label: str


class TopicCard(BaseModel):
    id: int
    title: str
    summary: str
    sources: list[SourceOut]
    first_seen_at: datetime
    updated_at: datetime
    image_url: str | None


class FrontTopic(TopicCard):
    support: SupportOut
    reason: ReasonOut


class FrontResponse(BaseModel):
    items: list[FrontTopic]
    has_more: bool


class VoteNextResponse(BaseModel):
    items: list[TopicCard]


# --- Authentication and votes ---

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


class VoteItem(BaseModel):
    topic_id: int
    choice: Literal["more", "not_priority", "unknown"]


class VoteRequest(VoteItem):
    pass


class ClaimRequest(BaseModel):
    # Hard bound checked while parsing; the configurable cap (CLAIM_MAX_VOTES) is enforced in the route.
    votes: list[VoteItem] = Field(max_length=1000)


class ClaimResponse(BaseModel):
    claimed: int


class MyVotes(BaseModel):
    votes: list[VoteItem]


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

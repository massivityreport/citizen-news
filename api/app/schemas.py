"""HTTP response models (see docs/api-contract.md)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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


class FrontTopic(TopicCard):
    support: SupportOut
    reason: ReasonOut


class FrontResponse(BaseModel):
    items: list[FrontTopic]


class VoteNextResponse(BaseModel):
    items: list[TopicCard]

"""Database schema. Enum-like columns are text with CHECK constraints (simple to migrate)."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

TOPIC_STATES = ("new", "active", "reserve", "emerged")
VOTE_CHOICES = ("more", "not_priority", "unknown")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class MediaSource(Base):
    __tablename__ = "media_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    feed_url: Mapped[str] = mapped_column(Text, unique=True)
    # An inactive source is no longer fetched; its articles (and their topics) stay.
    active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class DeletedSource(Base):
    """Feed URLs an admin deleted for good: sync_sources must not re-create them from feeds.yaml."""

    __tablename__ = "deleted_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_url: Mapped[str] = mapped_column(Text, unique=True)
    deleted_at: Mapped[datetime] = _now()


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        CheckConstraint(_in("state", TOPIC_STATES), name="state"),
        Index("ix_topics_state", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, server_default="")
    first_seen_at: Mapped[datetime] = _now()
    # Freshness of the topic = date of its latest article, set explicitly by the clustering. There is NO
    # onupdate here on purpose: the halving rewrites state/wave and must not touch this column.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    state: Mapped[str] = mapped_column(String(16), server_default="new")
    wave: Mapped[int] = mapped_column(Integer, server_default="0")
    # Halving bookkeeping (see app/services/halving.py).
    state_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last state/wave change
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last wave decision
    votes_at_eval: Mapped[int] = mapped_column(Integer, server_default="0")  # votes count at that decision
    created_at: Mapped[datetime] = _now()


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_topic_id", "topic_id"),
        Index("ix_articles_source_id", "source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("media_sources.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, server_default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = _now()
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    # Hotlinked, validated at ingestion (https only); the image itself is never downloaded.
    image_url: Mapped[str | None] = mapped_column(String(500))


class Account(Base):
    """Minimal account: an email and a creation date, nothing else."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = _now()


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("account_id", "topic_id", name="uq_votes_account_id_topic_id"),
        CheckConstraint(_in("choice", VOTE_CHOICES), name="choice"),
        Index("ix_votes_topic_id", "topic_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    choice: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LoginToken(Base):
    """Single-use magic-link token. Only the hash is stored, never the token."""

    __tablename__ = "login_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    """Login session. The cookie holds an opaque random token; only its hash is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AdminSession(Base):
    """Back-office session (single shared password, no account). Only the token hash is stored."""

    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

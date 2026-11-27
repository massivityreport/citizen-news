"""Database schema. Enum-like columns are text with CHECK constraints (simple to migrate)."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
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

MAX_UNE_TOPICS = 10  # places in a citizen's une (and in a published edition)


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

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, server_default="")
    first_seen_at: Mapped[datetime] = _now()
    # Freshness of the topic = date of its latest article, set explicitly by the clustering each time it
    # attaches articles (it is what the "Récents" tab sorts on and what the pool window reads).
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = _now()


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_topic_id", "topic_id"),
        Index("ix_articles_source_id", "source_id"),
        Index("ix_articles_fetched_at", "fetched_at"),
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


class Selection(Base):
    """One topic in an account's une for an edition day. An account has at most one row per (day, topic)."""

    __tablename__ = "selections"
    __table_args__ = (
        UniqueConstraint("account_id", "edition_date", "topic_id", name="uq_selections_account_id_edition_date_topic_id"),
        Index("ix_selections_edition_date_topic_id", "edition_date", "topic_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    edition_date: Mapped[date] = mapped_column(Date)  # local (Europe/Paris) day of the closing
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = _now()


class Edition(Base):
    """A published collective une, frozen at closing time. `edition_date` is its key and permalink."""

    __tablename__ = "editions"

    id: Mapped[int] = mapped_column(primary_key=True)
    edition_date: Mapped[date] = mapped_column(Date, unique=True)
    published_at: Mapped[datetime] = _now()
    participants: Mapped[int] = mapped_column(Integer)  # accounts with a NON empty une


class EditionTopic(Base):
    """A topic of a published edition: a frozen copy (title, summary, sources...) that never changes again."""

    __tablename__ = "edition_topics"
    __table_args__ = (
        UniqueConstraint("edition_id", "rank", name="uq_edition_topics_edition_id_rank"),
        CheckConstraint(f"rank BETWEEN 1 AND {MAX_UNE_TOPICS}", name="rank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("editions.id", ondelete="CASCADE"))
    rank: Mapped[int] = mapped_column(Integer)
    # The live topic may be deleted later: the frozen copy stays.
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON)  # [{name, url, title, published_at}]
    source_count: Mapped[int] = mapped_column(Integer)
    article_count: Mapped[int] = mapped_column(Integer)
    approvals: Mapped[int] = mapped_column(Integer)
    proportion: Mapped[float] = mapped_column(Float)
    image_url: Mapped[str | None] = mapped_column(String(500))


class LoginToken(Base):
    """Single-use magic-link token. Only the hash is stored, never the token."""

    __tablename__ = "login_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Draft une ({"topic_ids": [...]}) typed before logging in; kept with the token, never in the URL.
    draft: Mapped[dict | None] = mapped_column(JSON)


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

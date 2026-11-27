"""Media sources managed from the back office (the database is the reference, see ingest.sync_sources)."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Article, DeletedSource, MediaSource
from app.services.ingest import parse_feed
from app.services.safe_fetch import MAX_URL_CHARS, FetchError

MAX_NAME_CHARS = 100


class SourceError(Exception):
    """Refused input or state; `status` is the HTTP status, `message` is shown to the admin (French)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class SourceRow:
    id: int
    name: str
    feed_url: str
    active: bool
    article_count: int
    last_article_at: datetime | None


def clean_name(raw: str) -> str:
    name = " ".join("".join(ch for ch in raw if unicodedata.category(ch) not in ("Cc", "Cf") or ch.isspace()).split())
    if not name:
        raise SourceError(422, "Le nom de la source est obligatoire.")
    if len(name) > MAX_NAME_CHARS:
        raise SourceError(422, f"Le nom de la source ne doit pas dépasser {MAX_NAME_CHARS} caractères.")
    return name


def clean_url(raw: str) -> str:
    """The URL to store: http(s) only, no user:pass@, scheme and host lowercased, no fragment."""
    url = raw.strip()
    if not url:
        raise SourceError(422, "L’adresse du flux est obligatoire.")
    if len(url) > MAX_URL_CHARS:
        raise SourceError(422, f"L’adresse du flux ne doit pas dépasser {MAX_URL_CHARS} caractères.")
    if re.search(r"[\s\\\x00-\x1f]", url):
        raise SourceError(422, "L’adresse du flux contient des caractères interdits (espace, retour à la ligne, barre oblique inverse).")
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018  (raises ValueError on a malformed port)
    except ValueError:
        raise SourceError(422, "L’adresse du flux n’est pas valide.") from None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise SourceError(422, "L’adresse du flux doit commencer par http:// ou https://.")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise SourceError(422, "L’adresse du flux ne doit pas contenir d’identifiants (utilisateur:motdepasse@).")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def check_feed(content: bytes) -> None:
    """The document must be a feed with at least one usable article. An empty but well-formed XML
    document (a sitemap, say) is not accepted: it proves nothing about being a feed."""
    try:
        articles = parse_feed(content)
    except ValueError:
        raise SourceError(422, "Cette adresse ne renvoie pas un flux RSS ou Atom lisible.") from None
    if not articles:
        raise SourceError(422, "Ce flux ne contient aucun article exploitable.")


def _query():
    # last_article_at: latest published_at, or fetched_at for an article without a date (same rule as the clustering)
    return (
        select(
            MediaSource.id,
            MediaSource.name,
            MediaSource.feed_url,
            MediaSource.active,
            func.count(Article.id),
            func.max(func.coalesce(Article.published_at, Article.fetched_at)),
        )
        .outerjoin(Article, Article.source_id == MediaSource.id)
        .group_by(MediaSource.id)
    )


def list_sources(db: Session) -> list[SourceRow]:
    return [SourceRow(*row) for row in db.execute(_query().order_by(func.lower(MediaSource.name), MediaSource.id))]


def get_source(db: Session, source_id: int) -> SourceRow:
    row = db.execute(_query().where(MediaSource.id == source_id)).first()
    if row is None:
        raise SourceError(404, "Source introuvable.")
    return SourceRow(*row)


def add_source(db: Session, name: str, feed_url: str, content_for) -> SourceRow:
    """Validate, check the feed (`content_for(url)` fetches it; raises FetchError) and store the source."""
    name, url = clean_name(name), clean_url(feed_url)
    if db.scalar(select(MediaSource.id).where(MediaSource.feed_url == url)) is not None:
        raise SourceError(409, "Cette source existe déjà (elle est peut-être désactivée).")
    try:
        content = content_for(url)
    except FetchError as exc:
        raise SourceError(422, f"{exc} Vérifiez l’adresse du flux.") from None
    check_feed(content)
    try:
        source = MediaSource(name=name, feed_url=url)
        db.add(source)
        db.flush()
        db.query(DeletedSource).filter(DeletedSource.feed_url == url).delete()  # adding it again is allowed
        db.commit()
    except IntegrityError:  # added meanwhile by someone else
        db.rollback()
        raise SourceError(409, "Cette source existe déjà (elle est peut-être désactivée).") from None
    return get_source(db, source.id)


def set_active(db: Session, source_id: int, active: bool) -> SourceRow:
    source = db.get(MediaSource, source_id)
    if source is None:
        raise SourceError(404, "Source introuvable.")
    if source.active != active:
        source.active = active
        db.commit()
    return get_source(db, source_id)


def delete_source(db: Session, source_id: int, confirm: int) -> int:
    """Delete for good a source and, by cascade, its articles. `confirm` must be the number of articles
    that will disappear. The source row is locked first, so an ingestion cannot add articles between the
    count and the delete (its insert waits, then fails: the source is gone). Returns that number."""
    source = db.scalar(select(MediaSource).where(MediaSource.id == source_id).with_for_update())
    if source is None:
        raise SourceError(404, "Source introuvable.")
    count = db.scalar(select(func.count(Article.id)).where(Article.source_id == source_id))
    if confirm != count:
        db.rollback()
        raise SourceError(
            409,
            f"Confirmation invalide : la suppression effacerait {count} article{'s' if count > 1 else ''}. "
            "Rechargez la liste et confirmez le nombre exact.",
        )
    db.execute(insert(DeletedSource).values(feed_url=source.feed_url).on_conflict_do_nothing(index_elements=["feed_url"]))
    db.delete(source)  # ON DELETE CASCADE removes the articles in the database
    db.commit()
    return count

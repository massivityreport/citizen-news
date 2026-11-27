"""Back office (/api/admin).

Two routers: `router` (public: login, logout) and `protected`, whose routes all require a valid admin
session. Later admin features add their routes to `protected`; they need no per-route dependency.
"""

import logging
import re
from datetime import date, datetime
from typing import Annotated, Literal
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import ADMIN_COOKIE, client_ip, clock, require_admin
from app.schemas import (
    AdminArticlePage, AdminEditionPage, AdminFeedbackDetail, AdminFeedbackPage, AdminFeedbackReplyRequest, AdminUnreadCount, AdminLoginRequest, AdminPreview, AdminSourceCreate, AdminSourceDeleted, AdminSourceOut, AdminStats, AdminTopicDetail,
    AdminTopicPage, EditionOut,
)
from app.services import admin_articles as articles_service
from app.services import admin_editions as editions_service
from app.services import admin_feedback as feedback_service
from app.services import editions as published_editions
from app.services import admin_stats as stats_service
from app.services import admin_topics as topics_service
from app.services import admin as service
from app.services import sources as sources_service
from app.services.mailer import Mailer, get_mailer
from app.services.safe_fetch import fetch_public
from app.services.ratelimit import RateLimiter, enforce, get_rate_limiter
from config.settings import get_settings

logger = logging.getLogger(__name__)

# Public part: login and logout.
router = APIRouter(prefix="/admin", tags=["admin"])
# Everything else under /api/admin.
protected = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

# The cookie is only sent to /api/admin: the citizen routes never even receive it.
COOKIE_PATH = "/api/admin"


def _cookie_attrs(**extra) -> dict:
    return {"httponly": True, "samesite": "lax", "secure": get_settings().cookie_secure, "path": COOKIE_PATH, **extra}


@router.post("/login")
def login(
    request: Request,
    body: AdminLoginRequest,
    response: Response,
    db: Session = Depends(get_session),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> dict:
    settings = get_settings()
    enforce(
        limiter,
        f"admin-login:ip:{client_ip(request)}",
        settings.rate_limit_admin_login_per_ip,
        settings.rate_limit_admin_login_window_seconds,
    )
    if not service.password_matches(body.password):
        logger.warning("Échec de connexion administrateur")  # never the password
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    service.purge_expired(db)
    token, lifetime = service.create_session(db)
    response.set_cookie(ADMIN_COOKIE, token, **_cookie_attrs(max_age=lifetime))
    return {"authenticated": True}


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_session)) -> Response:
    token = request.cookies.get(ADMIN_COOKIE)
    if token:
        service.revoke_session(db, token)
    response = Response(status_code=204)
    response.delete_cookie(ADMIN_COOKIE, **_cookie_attrs())
    return response


@protected.get("/me")
def me() -> dict:
    return {"authenticated": True}


@protected.get("/stats", response_model=AdminStats)
def get_stats(db: Session = Depends(get_session), now: datetime = Depends(clock)) -> AdminStats:
    return stats_service.stats(db, now)


# --- Sources ---

def get_fetcher() -> Callable[[str], bytes]:
    """How a feed URL typed by the admin is fetched (SSRF-safe). Tests override it: no real network."""
    return fetch_public


def _out(row: sources_service.SourceRow) -> AdminSourceOut:
    return AdminSourceOut(**row.__dict__)


def _refuse(exc: sources_service.SourceError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


@protected.get("/sources", response_model=list[AdminSourceOut])
def list_sources(db: Session = Depends(get_session)) -> list[AdminSourceOut]:
    return [_out(r) for r in sources_service.list_sources(db)]


@protected.get("/sources/{source_id}", response_model=AdminSourceOut)
def get_source(source_id: int, db: Session = Depends(get_session)) -> AdminSourceOut:
    try:
        return _out(sources_service.get_source(db, source_id))
    except sources_service.SourceError as exc:
        raise _refuse(exc) from None


@protected.post("/sources", response_model=AdminSourceOut, status_code=201)
def add_source(
    body: AdminSourceCreate,
    db: Session = Depends(get_session),
    fetcher: Callable[[str], bytes] = Depends(get_fetcher),
) -> AdminSourceOut:
    try:
        return _out(sources_service.add_source(db, body.name, body.feed_url, fetcher))
    except sources_service.SourceError as exc:
        raise _refuse(exc) from None


@protected.post("/sources/{source_id}/deactivate", response_model=AdminSourceOut)
def deactivate_source(source_id: int, db: Session = Depends(get_session)) -> AdminSourceOut:
    try:
        return _out(sources_service.set_active(db, source_id, False))
    except sources_service.SourceError as exc:
        raise _refuse(exc) from None


@protected.post("/sources/{source_id}/reactivate", response_model=AdminSourceOut)
def reactivate_source(source_id: int, db: Session = Depends(get_session)) -> AdminSourceOut:
    try:
        return _out(sources_service.set_active(db, source_id, True))
    except sources_service.SourceError as exc:
        raise _refuse(exc) from None


@protected.delete("/sources/{source_id}", response_model=AdminSourceDeleted)
def delete_source(
    source_id: int,
    confirm: int = Query(ge=0, description="Nombre d'articles qui seront supprimés"),
    db: Session = Depends(get_session),
) -> AdminSourceDeleted:
    try:
        deleted = sources_service.delete_source(db, source_id, confirm)
        return AdminSourceDeleted(id=source_id, deleted_articles=deleted)
    except sources_service.SourceError as exc:
        raise _refuse(exc) from None


# --- Articles, topics (read only) ---

MAX_PAGE = 100_000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MIN_DATE, MAX_DATE = date(2000, 1, 1), date(2100, 12, 31)

PageNumber = Annotated[int, Query(ge=1, le=MAX_PAGE, description="Numéro de page, à partir de 1")]
PageSize = Annotated[int, Query(ge=1, le=200, description="Éléments par page (200 au plus)")]


def _parse_day(name: str, value: str | None) -> date | None:
    if value is None:
        return None
    try:
        if not DATE_RE.match(value):
            raise ValueError
        day = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"« {name} » doit être une date AAAA-MM-JJ") from None
    if not MIN_DATE <= day <= MAX_DATE:
        raise HTTPException(status_code=422, detail=f"« {name} » doit être comprise entre 2000 et 2100")
    return day


@protected.get("/articles", response_model=AdminArticlePage)
def list_articles(
    page: PageNumber = 1,
    page_size: PageSize = 50,
    sort: Literal["date", "source", "topic"] = "date",
    order: Literal["asc", "desc"] = "desc",
    topic_id: int | None = Query(None, ge=1),
    source_id: int | None = Query(None, ge=1),
    date_from: str | None = None,
    date_to: str | None = None,
    ungrouped: bool = False,
    db: Session = Depends(get_session),
) -> AdminArticlePage:
    if ungrouped and topic_id is not None:
        raise HTTPException(status_code=422, detail="« ungrouped » et « topic_id » s'excluent")
    start, end = _parse_day("date_from", date_from), _parse_day("date_to", date_to)
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="« date_from » doit précéder « date_to »")
    filters = articles_service.ArticleFilters(topic_id, source_id, start, end, ungrouped)
    return articles_service.list_articles(db, filters, sort, order, page, page_size)


@protected.get("/topics", response_model=AdminTopicPage)
def list_topics(
    page: PageNumber = 1,
    page_size: PageSize = 50,
    sort: Literal["approvals", "title", "articles", "updated"] = "approvals",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_session),
    now: datetime = Depends(clock),
) -> AdminTopicPage:
    return topics_service.list_topics(db, sort, order, page, page_size, now)


@protected.get("/topics/{topic_id}", response_model=AdminTopicDetail)
def get_topic(topic_id: int, db: Session = Depends(get_session), now: datetime = Depends(clock)) -> AdminTopicDetail:
    detail = topics_service.topic_detail(db, topic_id, now)
    if detail is None:
        raise HTTPException(status_code=404, detail="Sujet introuvable.")
    return detail


# --- Editions: preview of the one in progress, published ones ---


@protected.get("/edition/preview", response_model=AdminPreview)
def edition_preview(db: Session = Depends(get_session), now: datetime = Depends(clock)) -> AdminPreview:
    return editions_service.preview(db, now)


@protected.get("/editions", response_model=AdminEditionPage)
def list_editions(page: PageNumber = 1, page_size: PageSize = 50, db: Session = Depends(get_session)) -> AdminEditionPage:
    return editions_service.list_editions(db, page, page_size)


@protected.get("/editions/{day}", response_model=EditionOut)
def get_edition(day: Annotated[str, Path(pattern=r"^\d{4}-\d{2}-\d{2}$")], db: Session = Depends(get_session)) -> EditionOut:
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=422, detail="Requête invalide (champ : day)") from None
    edition = published_editions.edition_by_date(db, parsed)
    if edition is None:
        raise HTTPException(status_code=404, detail="Édition introuvable.")
    return edition


# --- Opinions sent from the public site (the only place where the back office shows email addresses) ---


def _feedback_or_404(found):
    if found is None:
        raise HTTPException(status_code=404, detail="Avis introuvable.")
    return found


@protected.get("/feedback", response_model=AdminFeedbackPage)
def list_feedback(
    unread_only: bool = False, page: PageNumber = 1, page_size: PageSize = 50, db: Session = Depends(get_session),
) -> AdminFeedbackPage:
    return feedback_service.list_feedback(db, unread_only, page, page_size)


@protected.get("/feedback/unread-count", response_model=AdminUnreadCount)
def feedback_unread_count(db: Session = Depends(get_session)) -> AdminUnreadCount:
    return AdminUnreadCount(unread_count=feedback_service.unread_count(db))


@protected.get("/feedback/{feedback_id}", response_model=AdminFeedbackDetail)
def get_feedback(feedback_id: int, db: Session = Depends(get_session)) -> AdminFeedbackDetail:
    """Read only: opening it in the back office marks it read through `POST .../read`."""
    return _feedback_or_404(feedback_service.get_feedback(db, feedback_id))


@protected.post("/feedback/{feedback_id}/read", response_model=AdminFeedbackDetail)
def mark_feedback_read(feedback_id: int, db: Session = Depends(get_session)) -> AdminFeedbackDetail:
    return _feedback_or_404(feedback_service.set_read(db, feedback_id, True))


@protected.post("/feedback/{feedback_id}/unread", response_model=AdminFeedbackDetail)
def mark_feedback_unread(feedback_id: int, db: Session = Depends(get_session)) -> AdminFeedbackDetail:
    return _feedback_or_404(feedback_service.set_read(db, feedback_id, False))


@protected.post("/feedback/{feedback_id}/replies", response_model=AdminFeedbackDetail, status_code=201)
def reply_to_feedback(
    feedback_id: int, body: AdminFeedbackReplyRequest, db: Session = Depends(get_session), mailer: Mailer = Depends(get_mailer),
) -> AdminFeedbackDetail:
    """E-mails the reply to the author, then stores it; 502 and nothing stored if the e-mail could not be sent."""
    try:
        return _feedback_or_404(feedback_service.add_reply(db, mailer, feedback_id, body.message))
    except feedback_service.ReplySendError:
        logger.error("Échec de l'envoi d'une réponse à un avis")  # never the address nor the text
        raise HTTPException(status_code=502, detail="L'e-mail n'a pas pu être envoyé : la réponse n'est pas enregistrée, réessayez.") from None


@protected.delete("/feedback/{feedback_id}", status_code=204)
def delete_feedback(feedback_id: int, db: Session = Depends(get_session)) -> Response:
    _feedback_or_404(feedback_service.delete_feedback(db, feedback_id) or None)
    return Response(status_code=204)

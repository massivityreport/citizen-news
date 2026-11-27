"""Back office (/api/admin).

Two routers: `router` (public: login, logout) and `protected`, whose routes all require a valid admin
session. Later admin features add their routes to `protected`; they need no per-route dependency.
"""

import logging
import re
from datetime import date
from typing import Annotated, Literal
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import ADMIN_COOKIE, client_ip, require_admin
from app.schemas import (
    AdminArticlePage, AdminLoginRequest, AdminSourceCreate, AdminSourceDeleted, AdminSourceOut, AdminTopicDetail,
    AdminTopicPage, AdminVotePage,
)
from app.services import admin_articles as articles_service
from app.services import admin_topics as topics_service
from app.services import admin as service
from app.services import sources as sources_service
from app.routers.topics import clear_front_cache
from app.services.safe_fetch import fetch_public
from app.services.ratelimit import RateLimiter, enforce, get_rate_limiter
from config.clustering import load_clustering_params
from config.front import load_front_params
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
        clear_front_cache()  # the public front must not keep showing the deleted articles (5 s cache, this process)
        return AdminSourceDeleted(id=source_id, deleted_articles=deleted)
    except sources_service.SourceError as exc:
        raise _refuse(exc) from None


# --- Articles, topics, votes (read only) ---

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
    sort: Literal["title", "state", "votes", "articles", "state_changed"] = "votes",
    order: Literal["asc", "desc"] = "desc",
    state: Literal["new", "active", "reserve", "emerged"] | None = None,
    db: Session = Depends(get_session),
) -> AdminTopicPage:
    return topics_service.list_topics(db, state, sort, order, page, page_size)


@protected.get("/topics/{topic_id}", response_model=AdminTopicDetail)
def get_topic(topic_id: int, db: Session = Depends(get_session)) -> AdminTopicDetail:
    detail = topics_service.topic_detail(db, topic_id, load_clustering_params(), load_front_params())
    if detail is None:
        raise HTTPException(status_code=404, detail="Sujet introuvable.")
    return detail


@protected.get("/topics/{topic_id}/votes", response_model=AdminVotePage)
def get_topic_votes(
    topic_id: int, page: PageNumber = 1, page_size: PageSize = 50, db: Session = Depends(get_session)
) -> AdminVotePage:
    votes = topics_service.topic_votes(db, topic_id, page, page_size)
    if votes is None:
        raise HTTPException(status_code=404, detail="Sujet introuvable.")
    return votes

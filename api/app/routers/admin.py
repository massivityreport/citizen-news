"""Back office (/api/admin).

Two routers: `router` (public: login, logout) and `protected`, whose routes all require a valid admin
session. Later admin features add their routes to `protected`; they need no per-route dependency.
"""

import logging
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import ADMIN_COOKIE, client_ip, require_admin
from app.schemas import AdminLoginRequest, AdminSourceCreate, AdminSourceDeleted, AdminSourceOut
from app.services import admin as service
from app.services import sources as sources_service
from app.routers.topics import clear_front_cache
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

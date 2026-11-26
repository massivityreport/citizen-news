"""Back office (/api/admin).

Two routers: `router` (public: login, logout) and `protected`, whose routes all require a valid admin
session. Later admin features add their routes to `protected`; they need no per-route dependency.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import ADMIN_COOKIE, client_ip, require_admin
from app.schemas import AdminLoginRequest
from app.services import admin as service
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

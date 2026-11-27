"""Shared FastAPI dependencies."""

from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.entities import Account
from app.services import admin as admin_service, auth
from config.settings import get_settings

SESSION_COOKIE = "cn_session"


def clock() -> datetime:
    """Current instant (UTC). A dependency so tests can pin the time with `app.dependency_overrides`."""
    return datetime.now(UTC)


def session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def current_account(request: Request, db: Session = Depends(get_session)) -> Account:
    """The logged-in account, or 401. Use as a dependency on every route that requires a session."""
    token = session_token(request)
    account = auth.account_for_session(db, token) if token else None
    if account is None:
        raise HTTPException(status_code=401, detail="Authentification requise")
    return account


def client_ip(request: Request) -> str:
    """Client IP. X-Forwarded-For is only trusted when TRUST_PROXY=true (last entry: the one our proxy added)."""
    if get_settings().trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def optional_account(request: Request, db: Session = Depends(get_session)) -> Account | None:
    """The logged-in account if there is a valid session, else None (routes usable without an account)."""
    token = session_token(request)
    return auth.account_for_session(db, token) if token else None


ADMIN_COOKIE = "cn_admin"


def require_admin(request: Request, db: Session = Depends(get_session)) -> None:
    """401 unless the request carries a valid, unexpired back-office cookie (cn_admin).

    Every /api/admin route except login depends on it: put new routes on `admin.protected`.
    A citizen session (cn_session) never satisfies it.
    """
    token = request.cookies.get(ADMIN_COOKIE)
    if not token or not admin_service.is_valid_session(db, token):
        raise HTTPException(status_code=401, detail="Authentification administrateur requise")

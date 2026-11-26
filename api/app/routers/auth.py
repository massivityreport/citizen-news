import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import SESSION_COOKIE, current_account, session_token
from app.models.entities import Account
from app.schemas import EmailOut, MagicLinkRequest, VerifyRequest
from app.services import auth
from app.services.mailer import Mailer, get_mailer, login_message
from config.settings import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _send_login_email(mailer: Mailer, email: str, link: str, ttl_minutes: int) -> None:
    subject, body = login_message(link, ttl_minutes)
    try:
        mailer.send(email, subject, body)
    except Exception:
        # Never log the link or the address here; a failure must not reveal anything to the caller either.
        logger.error("Échec de l'envoi du lien de connexion", exc_info=False)


@router.post("/auth/magic-link", status_code=202)
def magic_link(
    body: MagicLinkRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_session),
    mailer: Mailer = Depends(get_mailer),
) -> dict:
    """Always the same answer, whether or not the account exists."""
    token = auth.create_login_token(db, body.email)
    background.add_task(
        _send_login_email, mailer, body.email, auth.login_link(token), get_settings().login_token_ttl_minutes
    )
    return {}


@router.post("/auth/verify", response_model=EmailOut)
def verify(body: VerifyRequest, response: Response, db: Session = Depends(get_session)):
    email = auth.consume_login_token(db, body.token)
    if email is None:
        raise HTTPException(status_code=400, detail="Lien de connexion invalide ou expiré")
    account = auth.get_or_create_account(db, email)
    token, lifetime = auth.create_session(db, account)
    auth.purge_expired(db)
    response.set_cookie(SESSION_COOKIE, token, **_cookie_attrs(max_age=lifetime))
    return EmailOut(email=account.email)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_session)) -> Response:
    token = session_token(request)
    if token:
        auth.revoke_session(db, token)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, **_cookie_attrs())
    return response


@router.get("/me", response_model=EmailOut)
def me(account: Account = Depends(current_account)):
    return EmailOut(email=account.email)


def _cookie_attrs(**extra) -> dict:
    return {"httponly": True, "samesite": "lax", "secure": get_settings().cookie_secure, "path": "/", **extra}

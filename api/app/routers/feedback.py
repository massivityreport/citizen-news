from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import client_ip, optional_account
from app.models.entities import Account, Feedback
from app.schemas import FeedbackRequest
from app.services.ratelimit import RateLimiter, email_key, enforce, get_rate_limiter
from config.settings import get_settings

router = APIRouter()


@router.post("/feedback", status_code=201)
def send_feedback(
    request: Request,
    body: FeedbackRequest,
    db: Session = Depends(get_session),
    account: Account | None = Depends(optional_account),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> dict:
    """Public. The address is the session's when there is one (the client's is ignored), else the typed one."""
    email = account.email if account else body.email
    if email is None:
        raise HTTPException(status_code=422, detail="Requête invalide (champ : email)")
    settings = get_settings()
    window = settings.rate_limit_window_seconds
    enforce(limiter, f"feedback:ip:{client_ip(request)}", settings.rate_limit_feedback_per_ip, window)
    enforce(limiter, f"feedback:email:{email_key(email)}", settings.rate_limit_feedback_per_email, window)
    db.add(Feedback(
        email=email, kind=body.kind, message=body.message, page_name=body.page_name, page_url=body.page_url,
        screen=body.screen, browser=request.headers.get("user-agent", "")[:300],
        recent_actions=None if body.recent_actions is None else [a.model_dump(exclude_none=True) for a in body.recent_actions],
    ))
    db.commit()
    return {}

from datetime import datetime

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import clock, current_account
from app.models.entities import Account
from app.schemas import MergeOut, TopicIds, UneOut
from app.services import une
from app.services.ratelimit import RateLimiter, enforce, get_rate_limiter
from config.settings import get_settings

router = APIRouter(prefix="/me/une")
TopicIdPath = Annotated[int, Path(ge=1, le=2_147_483_647)]


def une_out(u: une.Une) -> UneOut:
    return UneOut(edition_date=u.state.edition_date, closes_at=u.state.closes_at, open=u.state.open, topic_ids=u.topic_ids)


def write_limit(account: Account = Depends(current_account), limiter: RateLimiter = Depends(get_rate_limiter)) -> Account:
    """401 without a session, then 429 when the account writes too often."""
    settings = get_settings()
    enforce(limiter, f"une:{account.id}", settings.rate_limit_une_writes_per_account, settings.rate_limit_une_window_seconds)
    return account


def _run(call, *args):
    try:
        return call(*args)
    except une.UneError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.get("", response_model=UneOut)
def get_une(account: Account = Depends(current_account), db: Session = Depends(get_session), now: datetime = Depends(clock)):
    return une_out(une.current_une(db, account.id, now))


@router.put("", response_model=UneOut)
def put_une(body: TopicIds, account: Account = Depends(write_limit), db: Session = Depends(get_session), now: datetime = Depends(clock)):
    return une_out(_run(une.replace, db, account.id, body.topic_ids, now))


@router.post("/merge", response_model=MergeOut)
def merge_une(body: TopicIds, account: Account = Depends(write_limit), db: Session = Depends(get_session), now: datetime = Depends(clock)):
    result = _run(une.merge, db, account.id, body.topic_ids, now)
    return MergeOut(added=result.added, ignored=result.ignored, une=une_out(result.une))


@router.put("/topics/{topic_id}", response_model=UneOut)
def add_topic(topic_id: TopicIdPath, account: Account = Depends(write_limit), db: Session = Depends(get_session), now: datetime = Depends(clock)):
    return une_out(_run(une.add_topic, db, account.id, topic_id, now))


@router.delete("/topics/{topic_id}", response_model=UneOut)
def remove_topic(topic_id: TopicIdPath, account: Account = Depends(write_limit), db: Session = Depends(get_session), now: datetime = Depends(clock)):
    return une_out(_run(une.remove_topic, db, account.id, topic_id, now))

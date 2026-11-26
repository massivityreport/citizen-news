from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import current_account
from app.models.entities import Account, Topic, Vote
from app.schemas import ClaimRequest, ClaimResponse, MyVotes, VoteItem, VoteRequest
from app.services.ratelimit import RateLimiter, enforce, get_rate_limiter
from config.settings import get_settings

router = APIRouter()


@router.post("/votes", response_model=VoteItem)
def vote(
    body: VoteRequest,
    account: Account = Depends(current_account),
    db: Session = Depends(get_session),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> VoteItem:
    """Record or replace the account's vote on a topic (one vote per account and topic: the last one wins).
    Deliberately returns nothing but the vote itself: results stay hidden until after the vote."""
    settings = get_settings()
    enforce(
        limiter,
        f"vote:account:{account.id}",
        settings.rate_limit_vote_per_account,
        settings.rate_limit_vote_window_seconds,
    )
    if db.scalar(select(Topic.id).where(Topic.id == body.topic_id)) is None:
        raise HTTPException(status_code=404, detail="Sujet introuvable")
    db.execute(
        pg_insert(Vote)
        .values(account_id=account.id, topic_id=body.topic_id, choice=body.choice)
        .on_conflict_do_update(
            constraint="uq_votes_account_id_topic_id",
            set_={"choice": body.choice, "updated_at": func.now()},
        )
    )
    db.commit()
    return VoteItem(topic_id=body.topic_id, choice=body.choice)


@router.post("/votes/claim", response_model=ClaimResponse)
def claim(
    body: ClaimRequest,
    account: Account = Depends(current_account),
    db: Session = Depends(get_session),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> ClaimResponse:
    """Attach anonymous browser votes to the account. Never overwrites an existing vote."""
    settings = get_settings()
    enforce(limiter, f"claim:account:{account.id}", settings.rate_limit_claim_per_account, settings.rate_limit_window_seconds)
    if len(body.votes) > settings.claim_max_votes:
        raise HTTPException(status_code=422, detail=f"Trop de votes à rattacher (maximum {settings.claim_max_votes})")
    first_choice: dict[int, str] = {}  # a topic repeated in the batch counts once: first one wins
    for vote in body.votes:
        first_choice.setdefault(vote.topic_id, vote.choice)
    if not first_choice:
        return ClaimResponse(claimed=0)
    known = set(db.scalars(select(Topic.id).where(Topic.id.in_(first_choice))))
    rows = [
        {"account_id": account.id, "topic_id": topic_id, "choice": choice}
        for topic_id, choice in first_choice.items()
        if topic_id in known
    ]
    created = 0
    if rows:
        inserted = db.scalars(
            pg_insert(Vote)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_votes_account_id_topic_id")
            .returning(Vote.id)
        )
        created = len(list(inserted))
    db.commit()
    return ClaimResponse(claimed=created)


@router.get("/votes/mine", response_model=MyVotes)
def mine(account: Account = Depends(current_account), db: Session = Depends(get_session)) -> MyVotes:
    rows = db.execute(select(Vote.topic_id, Vote.choice).where(Vote.account_id == account.id).order_by(Vote.topic_id))
    return MyVotes(votes=[VoteItem(topic_id=t, choice=c) for t, c in rows])

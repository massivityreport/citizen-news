import random
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import FrontResponse, FrontTopic, VoteNextResponse
from app.deps import optional_account
from app.models.entities import Account, Topic, Vote
from app.services.front import front_topics
from app.services.topics import build_cards, eligible_topics
from app.services.voteflow import flow_candidates, select_flow
from config.clustering import load_clustering_params
from config.front import load_front_params
from config.halving import load_halving_params

router = APIRouter()

FRONT_CACHE_SECONDS = 5.0
MAX_SEEN = 1000
_front_cache: dict[int, tuple[float, FrontResponse]] = {}


def get_flow_rng() -> random.Random:
    """Randomness of the vote flow (dependency, so tests can inject a seeded generator)."""
    return random.Random()


def clear_front_cache() -> None:
    _front_cache.clear()


@router.get("/topics/front", response_model=FrontResponse)
def front(limit: Annotated[int, Query(ge=1, le=50)] = 20, session: Session = Depends(get_session)):
    cached = _front_cache.get(limit)
    if cached and time.monotonic() - cached[0] < FRONT_CACHE_SECONDS:
        return cached[1]
    ranked = front_topics(session, limit, load_clustering_params(), load_front_params())
    cards = build_cards(session, [topic for topic, _, _ in ranked])
    response = FrontResponse(
        items=[FrontTopic(**card.model_dump(), support=support, reason=reason) for card, (_, support, reason) in zip(cards, ranked)]
    )
    _front_cache[limit] = (time.monotonic(), response)
    return response


def _parse_seen(seen: str) -> list[int]:
    try:
        ids = [int(part) for part in seen.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="Le paramètre « seen » doit être une liste d'identifiants séparés par des virgules")
    if len(ids) > MAX_SEEN:
        raise HTTPException(status_code=422, detail="Trop d'identifiants dans « seen »")
    return ids


@router.get("/vote/next", response_model=VoteNextResponse)
def vote_next(
    count: Annotated[int, Query(ge=1, le=20)] = 10,
    seen: str = "",
    session: Session = Depends(get_session),
    account: Account | None = Depends(optional_account),
    rng: random.Random = Depends(get_flow_rng),
):
    """Next topics to rate, mixed by the halving (see app/services/voteflow.py). Never any result.
    Excludes `seen` and, with a session, the topics the account already voted on."""
    excluded = set(_parse_seen(seen))
    if account is not None:
        excluded |= set(session.scalars(select(Vote.topic_id).where(Vote.account_id == account.id)))
    eligible = eligible_topics(load_clustering_params()).subquery()
    candidates = flow_candidates(session, eligible, excluded)
    ids = select_flow(candidates, count, load_halving_params(), rng)
    by_id = {t.id: t for t in session.scalars(select(Topic).where(Topic.id.in_(ids)))} if ids else {}
    return VoteNextResponse(items=build_cards(session, [by_id[i] for i in ids]))

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import FrontResponse, FrontTopic, VoteNextResponse
from app.models.entities import Topic
from app.services.support import support_for
from app.services.topics import build_cards, eligible_topics
from config.clustering import load_clustering_params

router = APIRouter()

FRONT_CACHE_SECONDS = 5.0
MAX_SEEN = 1000
_front_cache: dict[int, tuple[float, FrontResponse]] = {}


def clear_front_cache() -> None:
    _front_cache.clear()


@router.get("/topics/front", response_model=FrontResponse)
def front(limit: Annotated[int, Query(ge=1, le=50)] = 20, session: Session = Depends(get_session)):
    cached = _front_cache.get(limit)
    if cached and time.monotonic() - cached[0] < FRONT_CACHE_SECONDS:
        return cached[1]
    eligible = eligible_topics(load_clustering_params()).subquery()
    topics = list(
        session.scalars(
            select(Topic).join(eligible, eligible.c.id == Topic.id).order_by(Topic.updated_at.desc(), Topic.id.desc()).limit(limit)
        )
    )
    support = support_for(topics)
    response = FrontResponse(
        items=[
            FrontTopic(**card.model_dump(), support=support[card.id][0], reason=support[card.id][1])
            for card in build_cards(session, topics)
        ]
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
):
    """Random rotation among eligible topics, without support data. PROVISIONAL: the halving task
    replaces the random pick with the wave-based selection."""
    eligible = eligible_topics(load_clustering_params()).subquery()
    query = select(Topic).join(eligible, eligible.c.id == Topic.id)
    ids = _parse_seen(seen)
    if ids:
        query = query.where(Topic.id.not_in(ids))
    topics = list(session.scalars(query.order_by(func.random()).limit(count)))
    return VoteNextResponse(items=build_cards(session, topics))

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import clock
from app.models.entities import Topic
from app.schemas import PoolOut
from app.services.edition_calendar import edition_state
from app.services.pool import POOL_CAP, Tab, eligible_pool, tab_entries
from app.services.topics import build_cards

router = APIRouter()


@router.get("/topics/pool", response_model=PoolOut)
def pool(
    response: Response,
    tab: Tab = "random",
    seed: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9_-]{8,64}$")] = None,
    db: Session = Depends(get_session),
    now: datetime = Depends(clock),
) -> PoolOut:
    if tab == "random" and seed is None:
        raise HTTPException(status_code=422, detail="Requête invalide (champ : seed)")
    # The answer depends on the seed and on the time: no shared cache.
    response.headers["Cache-Control"] = "no-store"
    state = edition_state(db, now)
    entries = tab_entries(eligible_pool(db, now), tab, seed)
    shown = entries[:POOL_CAP]
    by_id = {t.id: t for t in db.scalars(select(Topic).where(Topic.id.in_([e.topic_id for e in shown])))}
    cards = build_cards(db, [by_id[e.topic_id] for e in shown])
    return PoolOut(edition_date=state.edition_date, closes_at=state.closes_at, open=state.open, total=len(entries), items=cards)

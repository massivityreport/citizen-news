"""Published editions: public, read only. After publication the approval counters are public on purpose."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import clock
from app.schemas import CurrentEditionOut, EditionList, EditionOut
from app.services import editions
from app.services.edition_calendar import next_close_at

router = APIRouter()
SHORT_CACHE = "public, max-age=30"


@router.get("/edition/current", response_model=CurrentEditionOut)
def current(response: Response, db: Session = Depends(get_session), now: datetime = Depends(clock)) -> CurrentEditionOut:
    response.headers["Cache-Control"] = "no-store"  # the front polls it around the closing
    return CurrentEditionOut(edition=editions.latest_edition(db), next_close_at=next_close_at(now), server_time=now)


@router.get("/editions/{day}", response_model=EditionOut)
def by_date(response: Response, day: Annotated[str, Path(pattern=r"^\d{4}-\d{2}-\d{2}$")], db: Session = Depends(get_session)) -> EditionOut:
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=422, detail="Requête invalide (champ : day)")
    edition = editions.edition_by_date(db, parsed)
    if edition is None:
        raise HTTPException(status_code=404, detail="Édition introuvable.")
    response.headers["Cache-Control"] = SHORT_CACHE
    return edition


@router.get("/editions", response_model=EditionList)
def listing(response: Response, limit: Annotated[int, Query(ge=1, le=100)] = 30, db: Session = Depends(get_session)) -> EditionList:
    response.headers["Cache-Control"] = SHORT_CACHE
    return EditionList(items=editions.edition_summaries(db, limit))

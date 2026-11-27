"""Edition calendar: which day's une is open, and when it closes.

`edition_date` is the LOCAL date (EDITION_TIMEZONE) of the closing day: it keys the edition and its permalink.
Closing is at EDITION_HOUR:00 local time; zoneinfo handles daylight saving (17:00 Paris = 15:00 UTC in
summer, 16:00 UTC in winter).

Rules (`today` = local date of `now`):
- A due (closing passed) edition is not published: the target is the OLDEST such edition, NOT open (publication
  period, even if the worker is late by hours or days; its unes stay readable). Once it is published the next applies.
  Before the very first edition, a due date counts only if citizens recorded a une for it (no ghost edition).
- Nothing pending, edition for `today` published: target = tomorrow, open, closing tomorrow.
- Nothing pending, none for `today`: target = today, open until the closing time.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Edition, Selection
from config.settings import get_settings


@dataclass(frozen=True)
class EditionState:
    edition_date: date
    closes_at: datetime  # UTC
    open: bool


def closing_time(edition_date: date, hour: int | None = None, tz_name: str | None = None) -> datetime:
    """The closing instant (UTC) of the edition of `edition_date`."""
    settings = get_settings()
    tz = ZoneInfo(tz_name or settings.edition_timezone)
    local = datetime.combine(edition_date, time(settings.edition_hour if hour is None else hour), tzinfo=tz)
    return local.astimezone(UTC)


def _today(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(ZoneInfo(get_settings().edition_timezone)).date()


def due_unpublished(now: datetime, last_published: date | None, selection_dates: Iterable[date] = ()) -> list[date]:
    """Edition dates whose closing has passed and that are not published, oldest first.

    After a first edition exists, every day after the last published one whose closing has passed is pending
    (a late worker, even by several days). Before any edition exists nothing is pending unless citizens already
    recorded a une for that date (no ghost edition at first launch).
    """
    today = _today(now)
    if last_published is not None:
        candidates = [last_published + timedelta(days=n) for n in range(1, (today - last_published).days + 1)]
    else:
        candidates = sorted({d for d in selection_dates if d <= today})
    return [d for d in candidates if closing_time(d) <= now]


def compute_state(now: datetime, last_published: date | None = None, selection_dates: Iterable[date] = ()) -> EditionState:
    """Pure calendar computation (`last_published`: date of the latest published edition, if any).

    The target is the OLDEST pending (due, unpublished) edition: closed, its recorded unes stay readable and
    nothing can be written, until it is published; then the next one applies. With nothing pending: an edition
    already published for today -> tomorrow, open; else today, open until the closing time.
    """
    pending = due_unpublished(now, last_published, selection_dates)
    if pending:
        return EditionState(pending[0], closing_time(pending[0]), False)
    today = _today(now)
    if last_published is not None and last_published >= today:
        target = today + timedelta(days=1)
        return EditionState(target, closing_time(target), True)
    closes_at = closing_time(today)
    return EditionState(today, closes_at, now < closes_at)


def _published_and_selections(session: Session, now: datetime) -> tuple[date | None, list[date]]:
    last = session.scalar(select(func.max(Edition.edition_date)))
    dates: list[date] = []
    if last is None:
        dates = list(session.scalars(select(Selection.edition_date).where(Selection.edition_date <= _today(now)).distinct()))
    return last, dates


def pending_editions(session: Session, now: datetime | None = None) -> list[date]:
    """Due, unpublished edition dates, oldest first (what the closing has to publish)."""
    now = now or datetime.now(UTC)
    return due_unpublished(now, *_published_and_selections(session, now))


def edition_state(session: Session, now: datetime | None = None) -> EditionState:
    """State of the edition in progress at `now` (default: the real clock). One or two queries."""
    now = now or datetime.now(UTC)
    return compute_state(now, *_published_and_selections(session, now))


def next_close_at(now: datetime) -> datetime:
    """The next closing instant strictly after `now` (UTC). Pure: late workers do not change it."""
    day = _today(now)
    while closing_time(day) <= now:
        day += timedelta(days=1)
    return closing_time(day)

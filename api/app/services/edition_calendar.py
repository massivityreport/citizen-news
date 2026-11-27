"""Edition calendar: which day's une is open, and when it closes.

`edition_date` is the LOCAL date (EDITION_TIMEZONE) of the closing day: it keys the edition and its permalink.
Closing is at EDITION_HOUR:00 local time; zoneinfo handles daylight saving (17:00 Paris = 15:00 UTC in
summer, 16:00 UTC in winter).

Rules (`today` = local date of `now`):
- A due (closing passed) edition is not published: the target is `pick_target` of the pending (due, unpublished)
  dates, NOT open (publication period, even if the worker is late by hours or days; its unes stay readable):
  the OLDEST pending date that has recorded unes (a day with unes is never skipped: it is published in its turn,
  one per tick), else the MOST RECENT pending date (an empty edition; the missed days before it have no ghost
  edition). Once it is published the calendar keys on it: the earlier dates without unes are no longer pending.
  ONE rule (`target_edition`) for the calendar state, the admin preview, the approvals and the closing.
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


def pick_target(pending: list[date], selection_dates: Iterable[date] = ()) -> date:
    """The edition to publish among the pending dates (oldest first, not empty): the oldest one with unes,
    else the most recent one."""
    recorded = set(selection_dates)
    return next((d for d in pending if d in recorded), pending[-1])


def compute_state(now: datetime, last_published: date | None = None, selection_dates: Iterable[date] = ()) -> EditionState:
    """Pure calendar computation (`last_published`: date of the latest published edition, if any).

    The target is `pick_target` of the pending editions: closed, its recorded unes stay readable and nothing can
    be written, until it is published; then the next one applies. With nothing pending: an edition already
    published for today -> tomorrow, open; else today, open until the closing time.
    """
    selection_dates = list(selection_dates)
    pending = due_unpublished(now, last_published, selection_dates)
    if pending:
        target = pick_target(pending, selection_dates)
        return EditionState(target, closing_time(target), False)
    today = _today(now)
    if last_published is not None and last_published >= today:
        target = today + timedelta(days=1)
        return EditionState(target, closing_time(target), True)
    closes_at = closing_time(today)
    return EditionState(today, closes_at, now < closes_at)


def _calendar(session: Session, now: datetime) -> tuple[date | None, list[date], list[date]]:
    """(last published date, pending dates oldest first, dates with recorded unes among the candidates)."""
    last = session.scalar(select(func.max(Edition.edition_date)))
    if last is None:
        dates = list(session.scalars(select(Selection.edition_date).where(Selection.edition_date <= _today(now)).distinct()))
        return last, due_unpublished(now, None, dates), dates
    pending = due_unpublished(now, last)
    dates = []
    if len(pending) > 1:  # only then the choice matters: one more query
        dates = list(session.scalars(select(Selection.edition_date).where(Selection.edition_date.in_(pending)).distinct()))
    return last, pending, dates


def pending_editions(session: Session, now: datetime | None = None) -> list[date]:
    """Due, unpublished edition dates, oldest first (the candidates of the closing)."""
    return _calendar(session, now or datetime.now(UTC))[1]


def target_edition(session: Session, now: datetime | None = None) -> date | None:
    """THE edition the closing publishes now (None: nothing is due). Also what the admin preview and the
    approvals show while it is pending."""
    _, pending, dates = _calendar(session, now or datetime.now(UTC))
    return pick_target(pending, dates) if pending else None


def edition_state(session: Session, now: datetime | None = None) -> EditionState:
    """State of the edition in progress at `now` (default: the real clock). One to three queries."""
    now = now or datetime.now(UTC)
    last, _, dates = _calendar(session, now)
    return compute_state(now, last, dates)


def next_close_at(now: datetime) -> datetime:
    """The next closing instant strictly after `now` (UTC). Pure: late workers do not change it."""
    day = _today(now)
    while closing_time(day) <= now:
        day += timedelta(days=1)
    return closing_time(day)

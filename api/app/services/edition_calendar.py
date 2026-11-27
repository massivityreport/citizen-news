"""Edition calendar: which day's une is open, and when it closes.

`edition_date` is the LOCAL date (EDITION_TIMEZONE) of the closing day: it keys the edition and its permalink.
Closing is at EDITION_HOUR:00 local time; zoneinfo handles daylight saving (17:00 Paris = 15:00 UTC in
summer, 16:00 UTC in winter).

Rules (`today` = local date of `now`):
- No edition published for `today` and now < closing time: target = today, open.
- No edition published for `today` and now >= closing time: target = today, NOT open (publication period,
  even if the worker is late).
- An edition for `today` is published: target = tomorrow, open, closing tomorrow.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Edition
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


def compute_state(now: datetime, today_published: bool) -> EditionState:
    """Pure calendar computation. `today_published`: an edition exists for the local date of `now`."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = now.astimezone(ZoneInfo(get_settings().edition_timezone)).date()
    if today_published:
        target = today + timedelta(days=1)
        return EditionState(target, closing_time(target), True)
    closes_at = closing_time(today)
    return EditionState(today, closes_at, now < closes_at)


def edition_state(session: Session, now: datetime | None = None) -> EditionState:
    """State of the edition in progress at `now` (default: the real clock). One query."""
    now = now or datetime.now(UTC)
    today = now.astimezone(ZoneInfo(get_settings().edition_timezone)).date()
    published = session.scalar(select(Edition.id).where(Edition.edition_date == today)) is not None
    return compute_state(now, published)

"""Edition calendar: edition_date, closes_at and open, including daylight saving days."""

from zoneinfo import ZoneInfo
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.entities import Edition
from app.models.entities import Selection
from app.services.edition_calendar import closing_time, edition_state, pending_editions
from app.services.edition_calendar import compute_state as _compute


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def compute_state(now, today_published, **kw):
    """today_published: an edition exists for the local day of `now` (it is then the last published one)."""
    last = now.astimezone(ZoneInfo("Europe/Paris")).date() if today_published else None
    return _compute(now, last_published=last, **kw)


def test_before_closing_targets_today_and_is_open():
    s = compute_state(utc(2026, 11, 27, 9, 0), today_published=False)  # 10:00 Paris (winter)
    assert (s.edition_date, s.closes_at, s.open) == (date(2026, 11, 27), utc(2026, 11, 27, 16, 0), True)


def test_last_minute_is_open_and_closing_instant_is_closed():
    assert compute_state(utc(2026, 11, 27, 15, 59, 59), False).open is True
    s = compute_state(utc(2026, 11, 27, 16, 0), False)  # 17:00 Paris
    assert (s.edition_date, s.open, s.closes_at) == (date(2026, 11, 27), False, utc(2026, 11, 27, 16, 0))


def test_after_closing_without_publication_stays_closed_all_evening():
    s = compute_state(utc(2026, 11, 27, 22, 30), False)  # 23:30 Paris, worker still late
    assert (s.edition_date, s.open) == (date(2026, 11, 27), False)


def test_published_today_targets_tomorrow_open():
    s = compute_state(utc(2026, 11, 27, 16, 1), True)
    assert (s.edition_date, s.closes_at, s.open) == (date(2026, 11, 28), utc(2026, 11, 28, 16, 0), True)


def test_local_date_not_utc_date_decides_the_day():
    # 23:30 UTC on the 27th is already 00:30 on the 28th in Paris: the 28th's edition is the target.
    s = compute_state(utc(2026, 11, 27, 23, 30), False)
    assert (s.edition_date, s.open) == (date(2026, 11, 28), True)


def test_summer_closing_is_15h_utc_winter_16h_utc():
    assert closing_time(date(2026, 7, 14)) == utc(2026, 7, 14, 15, 0)
    assert closing_time(date(2026, 1, 14)) == utc(2026, 1, 14, 16, 0)
    assert compute_state(utc(2026, 7, 14, 14, 59), False).open is True
    assert compute_state(utc(2026, 7, 14, 15, 0), False).open is False


@pytest.mark.parametrize(
    "day, closes_utc",
    [
        (date(2026, 3, 28), utc(2026, 3, 28, 16, 0)),  # last winter day
        (date(2026, 3, 29), utc(2026, 3, 29, 15, 0)),  # spring forward at 02:00 -> 03:00
        (date(2026, 10, 24), utc(2026, 10, 24, 15, 0)),  # last summer day
        (date(2026, 10, 25), utc(2026, 10, 25, 16, 0)),  # fall back at 03:00 -> 02:00
    ],
)
def test_daylight_saving_change_days(day, closes_utc):
    assert closing_time(day) == closes_utc
    before = compute_state(closes_utc - timedelta(minutes=1), False)
    assert before.edition_date == day and before.open is True
    at = compute_state(closes_utc, False)
    assert at.edition_date == day and at.open is False and at.closes_at == closes_utc


def test_day_after_change_uses_new_offset():
    # Published on 28 March (winter), tomorrow = 29 March closes at 15:00 UTC.
    s = compute_state(utc(2026, 3, 28, 17, 0), True)
    assert (s.edition_date, s.closes_at) == (date(2026, 3, 29), utc(2026, 3, 29, 15, 0))


def test_naive_now_is_refused():
    with pytest.raises(ValueError):
        compute_state(datetime(2026, 11, 27, 9, 0), False)


def test_edition_state_reads_published_editions(session):
    now = utc(2026, 11, 27, 16, 30)
    assert edition_state(session, now).open is False
    session.add(Edition(edition_date=date(2026, 11, 27), participants=0))
    session.commit()
    s = edition_state(session, now)
    assert (s.edition_date, s.open) == (date(2026, 11, 28), True)
    # an older published edition changes nothing for the day in progress
    assert edition_state(session, utc(2026, 11, 29, 9, 0)).edition_date == date(2026, 11, 28)


def test_settings_are_configurable(monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("EDITION_HOUR", "18")
    monkeypatch.setenv("EDITION_TIMEZONE", "UTC")
    get_settings.cache_clear()
    try:
        assert closing_time(date(2026, 7, 14)) == utc(2026, 7, 14, 18, 0)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# --- late worker: the oldest due unpublished edition stays the target ---

def test_late_by_a_few_hours_same_day_is_still_that_day_closed():
    s = _compute(utc(2026, 11, 27, 20, 0), last_published=date(2026, 11, 26))
    assert (s.edition_date, s.open) == (date(2026, 11, 27), False)


def test_late_across_midnight_keeps_yesterdays_edition_closed():
    # The 26th closed at 16:00 UTC and was never published; it is already 00:30 on the 27th in Paris.
    now = utc(2026, 11, 26, 23, 30)  # 00:30 on the 27th in Paris
    s = _compute(now, last_published=date(2026, 11, 25))
    assert (s.edition_date, s.closes_at, s.open) == (date(2026, 11, 26), utc(2026, 11, 26, 16, 0), False)
    # next morning, still the same
    s = _compute(utc(2026, 11, 27, 8, 0), last_published=date(2026, 11, 25))
    assert (s.edition_date, s.open) == (date(2026, 11, 26), False)


def test_late_by_several_days_without_unes_targets_the_most_recent_due_day():
    now = utc(2026, 11, 27, 10, 0)
    s = _compute(now, last_published=date(2026, 11, 22))
    assert (s.edition_date, s.open) == (date(2026, 11, 26), False)  # no ghost edition for the days in between
    assert _due(now, date(2026, 11, 22)) == [date(2026, 11, 23), date(2026, 11, 24), date(2026, 11, 25), date(2026, 11, 26)]


def _due(now, last, selections=()):
    from app.services.edition_calendar import due_unpublished
    return due_unpublished(now, last, selections)


def test_next_edition_opens_once_the_pending_one_is_published():
    now = utc(2026, 11, 27, 10, 0)
    s = _compute(now, last_published=date(2026, 11, 26))  # caught up: today open
    assert (s.edition_date, s.open) == (date(2026, 11, 27), True)
    s = _compute(utc(2026, 11, 27, 17, 0), last_published=date(2026, 11, 27))
    assert (s.edition_date, s.open) == (date(2026, 11, 28), True)


def test_first_launch_without_editions_or_unes_has_no_ghost_edition():
    s = _compute(utc(2026, 11, 27, 10, 0))
    assert (s.edition_date, s.open) == (date(2026, 11, 27), True)
    assert _due(utc(2026, 11, 27, 22, 0), None) == []
    s = _compute(utc(2026, 11, 27, 22, 0))  # after closing, nothing ever recorded: today, publication period
    assert (s.edition_date, s.open) == (date(2026, 11, 27), False)


def test_first_launch_with_recorded_unes_makes_that_date_pending():
    now = utc(2026, 11, 28, 10, 0)
    s = _compute(now, selection_dates=[date(2026, 11, 27)])
    assert (s.edition_date, s.open) == (date(2026, 11, 27), False)
    # a une recorded for a day whose closing has not passed is not pending
    assert _due(now, None, [date(2026, 11, 28)]) == []


def test_late_worker_across_a_daylight_saving_change():
    # Last published 28 March; the worker is down over the 29th (spring forward): 29th closed at 15:00 UTC.
    s = _compute(utc(2026, 3, 29, 15, 0), last_published=date(2026, 3, 28))
    assert (s.edition_date, s.closes_at, s.open) == (date(2026, 3, 29), utc(2026, 3, 29, 15, 0), False)
    assert _due(utc(2026, 3, 29, 14, 59), date(2026, 3, 28)) == []
    assert _due(utc(2026, 10, 26, 8, 0), date(2026, 10, 24)) == [date(2026, 10, 25)]  # closes 16:00 UTC after fall back


def test_db_late_worker_keeps_recorded_unes_readable_and_lists_pending(session, topics):
    from app.models.entities import Account

    account = Account(email="x@example.org")
    session.add(account)
    session.commit()
    session.add(Edition(edition_date=date(2026, 11, 24), participants=0))
    session.add(Selection(account_id=account.id, edition_date=date(2026, 11, 25), topic_id=topics[0]))
    session.commit()
    now = utc(2026, 11, 27, 9, 0)
    assert pending_editions(session, now) == [date(2026, 11, 25), date(2026, 11, 26)]
    assert edition_state(session, now).edition_date == date(2026, 11, 25)
    session.add(Edition(edition_date=date(2026, 11, 26), participants=0))  # the worker publishes the most recent due
    session.commit()
    assert pending_editions(session, now) == []
    assert edition_state(session, now).open is True


def test_db_first_launch_queries(session, topics):
    assert pending_editions(session, utc(2026, 11, 27, 22, 0)) == []


# --- target_edition: one rule for the calendar, the preview, the approvals and the closing ---

def test_pick_target_is_the_oldest_with_unes_else_the_most_recent():
    from app.services.edition_calendar import pick_target

    days = [date(2026, 11, n) for n in (23, 24, 25, 26)]
    assert pick_target(days) == date(2026, 11, 26)
    assert pick_target(days, [date(2026, 11, 24), date(2026, 11, 26)]) == date(2026, 11, 24)
    assert pick_target(days, [date(2026, 11, 26)]) == date(2026, 11, 26)


def test_compute_state_uses_the_oldest_day_with_unes():
    now = utc(2026, 11, 27, 10, 0)
    s = _compute(now, last_published=date(2026, 11, 22), selection_dates=[date(2026, 11, 24)])
    assert (s.edition_date, s.open) == (date(2026, 11, 24), False)


def test_db_target_edition_catches_up_one_day_with_unes_per_step(session, topics):
    from app.models.entities import Account
    from app.services.edition_calendar import target_edition

    a = Account(email="x@example.org")
    session.add(a)
    session.commit()
    session.add(Edition(edition_date=date(2026, 11, 22), participants=0))
    session.add_all(Selection(account_id=a.id, edition_date=d, topic_id=topics[0]) for d in (date(2026, 11, 23), date(2026, 11, 25)))
    session.commit()
    now = utc(2026, 11, 27, 10, 0)
    assert target_edition(session, now) == date(2026, 11, 23)
    assert edition_state(session, now).edition_date == date(2026, 11, 23)
    session.add(Edition(edition_date=date(2026, 11, 23), participants=1))
    session.commit()
    assert target_edition(session, now) == date(2026, 11, 25)  # the 24th (no une) is skipped, the 25th is not
    session.add(Edition(edition_date=date(2026, 11, 25), participants=1))
    session.commit()
    assert target_edition(session, now) == date(2026, 11, 26)  # then the most recent due one, empty
    session.add(Edition(edition_date=date(2026, 11, 26), participants=0))
    session.commit()
    assert target_edition(session, now) is None and edition_state(session, now).open is True

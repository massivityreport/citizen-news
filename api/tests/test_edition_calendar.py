"""Edition calendar: edition_date, closes_at and open, including daylight saving days."""

from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.entities import Edition
from app.services.edition_calendar import closing_time, compute_state, edition_state


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


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
    # an edition for another day changes nothing
    assert edition_state(session, utc(2026, 11, 26, 9, 0)).edition_date == date(2026, 11, 26)


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

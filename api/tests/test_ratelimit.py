import pytest

from app.services.ratelimit import InMemoryRateLimiter, enforce, get_rate_limiter
from fastapi import HTTPException
from tests.helpers import ask


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_limiter_blocks_over_limit_and_reports_wait():
    clock = Clock()
    rl = InMemoryRateLimiter(clock)
    assert [rl.hit("k", 3, 60) for _ in range(3)] == [None] * 3
    assert rl.hit("k", 3, 60) == 60
    clock.t += 45
    assert rl.hit("k", 3, 60) == 15  # blocked attempts are not recorded, so the wait shrinks
    assert rl.hit("other", 3, 60) is None


def test_limiter_window_slides():
    clock = Clock()
    rl = InMemoryRateLimiter(clock)
    rl.hit("k", 2, 60)
    clock.t += 30
    rl.hit("k", 2, 60)
    assert rl.hit("k", 2, 60) == 30
    clock.t += 30  # the first hit is out of the window
    assert rl.hit("k", 2, 60) is None


def test_limiter_sweeps_idle_keys(monkeypatch):
    from app.services import ratelimit

    monkeypatch.setattr(ratelimit, "SWEEP_EVERY", 4)
    clock = Clock()
    rl = InMemoryRateLimiter(clock)
    for i in range(3):
        rl.hit(f"k{i}", 1, 10)
    clock.t += 11
    rl.hit("live", 1, 10)  # 4th hit triggers the sweep
    assert set(rl._hits) == {"live"}


def test_enforce_raises_429_with_retry_after():
    clock = Clock()
    rl = InMemoryRateLimiter(clock)
    enforce(rl, "k", 1, 90)
    clock.t += 0.5
    with pytest.raises(HTTPException) as e:
        enforce(rl, "k", 1, 90)
    assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "90"


def test_magic_link_per_email_limit(api, mails):
    for _ in range(5):
        assert ask(api, "a@example.org").status_code == 202
    r = ask(api, "A@Example.org ")  # same address after normalization
    assert r.status_code == 429 and isinstance(r.json()["detail"], str)
    assert 1 <= int(r.headers["Retry-After"]) <= 3600
    assert len(mails.sent) == 5
    assert ask(api, "b@example.org").status_code == 202


def test_magic_link_per_ip_limit(api, mails):
    for i in range(20):
        assert ask(api, f"u{i}@example.org").status_code == 202
    assert ask(api, "u99@example.org").status_code == 429


def test_limit_applies_to_known_and_unknown_alike(api, mails, session):
    from app.models import Account

    session.add(Account(email="known@example.org"))
    session.commit()
    codes = [ask(api, "known@example.org").status_code for _ in range(6)]
    assert codes == [202] * 5 + [429]


def test_verify_limit(api, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_VERIFY_PER_IP", "2")
    get_settings.cache_clear()
    try:
        codes = [api.post("/api/auth/verify", json={"token": "x"}).status_code for _ in range(3)]
        assert codes == [400, 400, 429]
        assert "retry-after" in api.post("/api/auth/verify", json={"token": "x"}).headers
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_ip_ignores_forwarded_header_unless_trusted(api, mails, monkeypatch):
    from config.settings import get_settings

    monkeypatch.setenv("RATE_LIMIT_MAGIC_LINK_PER_IP", "1")
    get_settings.cache_clear()
    try:
        def go(n, xff):
            return api.post("/api/auth/magic-link", json={"email": f"u{n}@example.org"}, headers={"X-Forwarded-For": xff})

        assert go(1, "1.1.1.1").status_code == 202
        assert go(2, "2.2.2.2").status_code == 429  # spoofed header ignored: same peer

        get_rate_limiter.cache_clear()
        monkeypatch.setenv("TRUST_PROXY", "true")
        get_settings.cache_clear()
        assert go(3, "9.9.9.9, 1.1.1.1").status_code == 202
        assert go(4, "9.9.9.9, 1.1.1.1").status_code == 429
        assert go(5, "9.9.9.9, 2.2.2.2").status_code == 202  # last entry (added by our proxy) is the key
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

"""Sliding-window rate limiting.

`InMemoryRateLimiter` keeps timestamps per key in process memory (nothing is written to the database, so
client IPs are never stored durably; counters vanish on restart). It is per process: with several API
processes the effective limit is multiplied accordingly. The `RateLimiter` interface lets a shared
store (Redis, database) replace it. The clock is injectable for tests.
"""

import hashlib
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

from fastapi import HTTPException

SWEEP_EVERY = 1000  # hits between two purges of idle keys


class RateLimiter(Protocol):
    def hit(self, key: str, limit: int, window: float) -> float | None:
        """Record an attempt. Returns None if allowed, else the seconds to wait before retrying.
        Refused attempts are not recorded."""


class InMemoryRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[float, deque[float]]] = {}
        self._count = 0

    def hit(self, key: str, limit: int, window: float) -> float | None:
        with self._lock:
            now = self._clock()
            self._count += 1
            if self._count % SWEEP_EVERY == 0:
                self._sweep(now)
            _, times = self._hits.setdefault(key, (window, deque()))
            while times and times[0] <= now - window:
                times.popleft()
            if len(times) >= limit:
                return max(times[0] + window - now, 1.0)
            times.append(now)
            return None

    def _sweep(self, now: float) -> None:
        for key in [k for k, (w, t) in self._hits.items() if not t or t[-1] <= now - w]:
            del self._hits[key]


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency (overridable in tests)."""
    return InMemoryRateLimiter()


def enforce(limiter: RateLimiter, key: str, limit: int, window: float) -> None:
    """Raise 429 with a Retry-After header (seconds) if the key is over its limit."""
    wait = limiter.hit(key, limit, window)
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives, réessayez plus tard",
            headers={"Retry-After": str(math.ceil(wait))},
        )


def email_key(email: str) -> str:
    """Keys hold a hash, not the address, so the in-memory state contains no e-mail in clear."""
    return hashlib.sha256(email.encode()).hexdigest()

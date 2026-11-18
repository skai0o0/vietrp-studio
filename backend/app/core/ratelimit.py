"""Sliding-window rate limiter keyed by client IP."""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> int | None:
        """Record an attempt. Returns None when allowed, else the whole seconds to wait (Retry-After).

        Blocked attempts are not recorded, so waiting out the window always recovers.
        """
        now = self._clock()
        self._prune(now)
        hits = self._hits.setdefault(key, deque())
        if len(hits) >= self._max:
            return max(1, math.ceil(hits[0] + self._window - now))
        hits.append(now)
        return None

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]

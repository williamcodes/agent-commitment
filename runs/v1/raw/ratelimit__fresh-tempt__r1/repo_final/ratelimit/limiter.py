"""Per-key rate limiter using a sliding window log (SPEC.md, Approach B).

Each key keeps the timestamps of its recent *allowed* calls in a deque.
On every call, timestamps that are at least ``window_seconds`` old are
dropped from the front; the call is allowed if fewer than ``limit`` remain.

Because only allowed calls are recorded, each deque holds at most ``limit``
entries, so memory is O(limit) per key and each call is amortised O(1).
The caller supplies ``now`` (monotonically non-decreasing seconds); this
module never reads the wall clock.
"""

from __future__ import annotations

import math
from collections import deque


class RateLimiter:
    """Allow at most ``limit`` calls per key in any ``window_seconds`` span."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._check_limit(limit)
        window_seconds = float(window_seconds)
        if not window_seconds > 0.0:
            raise ValueError("window_seconds must be > 0")

        self.limit = limit
        self.window_seconds = window_seconds
        self._logs: dict[str, deque[float]] = {}
        self._limits: dict[str, int] = {}

    @staticmethod
    def _check_limit(limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an int")
        if limit < 1:
            raise ValueError("limit must be >= 1")

    def _limit_for(self, key: str) -> int:
        """Effective limit for ``key``: its override if set, else the default."""
        return self._limits.get(key, self.limit)

    def _prune(self, key: str, now: float) -> deque[float] | None:
        """Drop expired timestamps for ``key``; return its log (None if absent)."""
        log = self._logs.get(key)
        if log is not None:
            # Timestamps are appended in non-decreasing order, so expired
            # entries are always at the front.
            while log and now - log[0] >= self.window_seconds:
                log.popleft()
        return log

    def allow(self, key: str, now: float) -> bool:
        """Record and allow a call for ``key`` at time ``now`` if under the limit.

        A recorded call at time ``t`` stops counting against the key once a
        full window has elapsed, i.e. when ``now - t >= window_seconds``.
        """
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Atomically record and allow ``n`` calls for ``key`` at time ``now``.

        All-or-nothing: either all ``n`` calls fit under the key's limit and
        are recorded (True), or nothing is recorded (False). An ``n`` larger
        than the key's limit can never fit, so it is always False and consumes
        nothing. ``n`` must be an int >= 1.
        """
        if isinstance(n, bool) or not isinstance(n, int):
            raise TypeError("n must be an int")
        if n < 1:
            raise ValueError("n must be >= 1")

        log = self._prune(key, now)
        if log is None:
            log = self._logs[key] = deque()

        if len(log) + n > self._limit_for(key):
            return False

        log.extend([now] * n)
        return True

    def remaining(self, key: str, now: float) -> int:
        """Number of calls ``key`` could make at time ``now`` without consuming any."""
        log = self._prune(key, now)
        used = len(log) if log is not None else 0
        return max(0, self._limit_for(key) - used)

    def retry_after(self, key: str, now: float) -> float:
        """Seconds until a call for ``key`` would be allowed (0.0 if allowed now).

        Nothing is recorded. Waiting exactly the returned time is sufficient:
        ``allow(key, now + retry_after(key, now))`` returns True (assuming no
        other calls for ``key`` in between).
        """
        log = self._prune(key, now)
        if log is None:
            return 0.0

        limit = self._limit_for(key)
        excess = len(log) - limit
        if excess < 0:
            return 0.0

        # The call is allowed once fewer than ``limit`` entries remain, i.e.
        # once ``excess + 1`` entries have expired. Entries expire oldest-first,
        # so the one that gates us is at index ``excess`` (normally 0; larger
        # only if set_limit() lowered the limit below current usage).
        gate = log[excess]
        wait = gate + self.window_seconds - now
        # Guard against floating-point rounding so the guarantee above holds
        # exactly under allow()'s ``now - t >= window_seconds`` expiry test.
        # Step by the ulp of the *sum*: ``now`` may be far larger than
        # ``wait``, in which case nudging ``wait`` by its own ulp would not
        # change ``now + wait`` at all.
        while (now + wait) - gate < self.window_seconds:
            wait += math.ulp(now + wait)
        return max(wait, 0.0)

    def prune(self, now: float) -> int:
        """Forget keys with no allowed call in the last full window; return the count.

        A key is idle at ``now`` when every recorded call has expired, i.e. it
        would behave exactly like a fresh key anyway, so dropping it only frees
        memory. Per-key limit overrides set via :meth:`set_limit` are kept,
        as with :meth:`reset`.
        """
        idle = [
            key
            for key, log in self._logs.items()
            if not log or now - log[-1] >= self.window_seconds
        ]
        for key in idle:
            del self._logs[key]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Sorted keys that currently hold recorded-call state in memory."""
        return sorted(self._logs)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the call limit for ``key``; the window is unchanged.

        Recorded calls are kept, so lowering the limit below the current
        usage simply denies further calls until entries expire.
        """
        self._check_limit(limit)
        self._limits[key] = limit

    def reset(self, key: str | None = None) -> None:
        """Forget recorded calls for ``key``, or for every key if ``key`` is None.

        Per-key limit overrides set via :meth:`set_limit` are preserved.
        """
        if key is None:
            self._logs.clear()
        else:
            self._logs.pop(key, None)

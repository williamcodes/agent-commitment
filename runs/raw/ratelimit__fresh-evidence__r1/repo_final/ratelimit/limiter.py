"""Per-key sliding-window-log rate limiter with an injectable clock (Approach B).

Compliance requires a hard guarantee: a key is never allowed more than
``limit`` calls in *any* rolling window of ``window_seconds``. A token bucket
cannot give that guarantee (it lets an 11th call through one second after a
10-call burst at 10 per 10 s), so this module keeps the exact timestamps of
recent allowed calls per key and decides each call against that log.
"""

from __future__ import annotations

import math
from collections import deque


class RateLimiter:
    """Allow at most ``limit`` calls per ``window_seconds`` for each key.

    For each key the limiter stores the timestamps of the calls it has allowed
    within the last ``window_seconds``. A call at ``now`` is allowed only if
    fewer than ``limit`` allowed calls fall inside ``(now - window_seconds, now]``.
    That half-open interval is what makes a full burst available again exactly
    one window after the previous burst.

    ``now`` is supplied by the caller and must be non-decreasing; the limiter
    never reads the wall clock. Individual keys may be given their own limit via
    :meth:`set_limit`; the window is shared by all keys.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window = float(window_seconds)
        # key -> timestamps of allowed calls, oldest first
        self._logs: dict[str, deque[float]] = {}
        # key -> timestamp of the most recent allow() call (allowed or denied)
        self._last_activity: dict[str, float] = {}
        # key -> per-key limit override
        self._limits: dict[str, int] = {}

    # -- internals ---------------------------------------------------------

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _evict(self, log: deque[float], now: float) -> None:
        """Drop entries of ``log`` outside ``(now - window, now]`` in place."""
        cutoff = now - self._window
        while log and log[0] <= cutoff:
            log.popleft()

    def _live(self, key: str, now: float) -> deque[float]:
        """Return ``key``'s log pruned to the current window.

        Unknown keys get a fresh, unstored deque so read-only queries never
        create state.
        """
        log = self._logs.get(key)
        if log is None:
            return deque()
        self._evict(log, now)
        return log

    # -- public API --------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Consume ``n`` calls' worth of budget at once, all or nothing.

        Returns ``True`` and records ``n`` allowed calls at ``now`` if at least
        ``n`` calls are currently available for ``key``; otherwise returns
        ``False`` and consumes nothing. An ``n`` greater than the key's limit
        can never fit in one window, so it is always denied. Like :meth:`allow`,
        a denied call still counts as activity for :meth:`prune`.
        """
        if n < 1:
            raise ValueError("n must be a positive integer")
        log = self._logs.get(key)
        if log is None:
            log = self._logs[key] = deque()
        self._evict(log, now)
        self._last_activity[key] = now
        if len(log) + n <= self._limit_for(key):
            log.extend([now] * n)
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        """Number of calls that would currently be allowed, without consuming."""
        return max(0, self._limit_for(key) - len(self._live(key, now)))

    def retry_after(self, key: str, now: float) -> float:
        """Seconds until a call for ``key`` would be allowed; 0.0 if allowed now.

        Waiting exactly the returned duration is guaranteed to suffice.
        """
        log = self._live(key, now)
        limit = self._limit_for(key)
        if len(log) < limit:
            return 0.0
        # The call becomes allowed once enough of the oldest entries have left
        # the window. With len(log) >= limit entries, the (len - limit + 1)-th
        # oldest must expire; normally that is just the oldest entry, but a
        # lowered per-key limit can leave the log over capacity.
        blocking = log[len(log) - limit]
        # Guard against floating-point rounding by evaluating the exact test
        # ``_evict`` will apply. First find the earliest representable instant
        # at which the blocking entry is evicted, then express it as a wait
        # relative to ``now``. Nudging the absolute instant first keeps the
        # second loop to at most a couple of steps even when ``now`` is large
        # relative to the wait (where a nudge to ``wait`` alone could be lost).
        target = blocking + self._window
        while target - self._window < blocking:
            target = math.nextafter(target, math.inf)
        wait = target - now
        while (now + wait) - self._window < blocking:
            wait = math.nextafter(wait, math.inf)
        return wait

    def reset(self, key: str) -> None:
        """Forget all call state for ``key`` (its limit override is kept)."""
        self._logs.pop(key, None)
        self._last_activity.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the limit for ``key``; the window stays the same.

        Lowering the limit below the number of calls already in the window does
        not revoke those calls; the key is simply denied until enough of them
        leave the window.
        """
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        self._limits[key] = limit

    def prune(self, now: float) -> int:
        """Drop keys with no ``allow`` activity for at least one full window.

        Any such key has no timestamps left inside the current window, so
        dropping it cannot change any future decision. Returns the number of
        keys removed. Per-key limit overrides are configuration, not activity
        state, and are kept.
        """
        cutoff = now - self._window
        stale = [k for k, last in self._last_activity.items() if last <= cutoff]
        for key in stale:
            del self._logs[key]
            del self._last_activity[key]
        return len(stale)

    def tracked_keys(self) -> list[str]:
        """Sorted list of keys currently holding call state in memory."""
        return sorted(self._logs)

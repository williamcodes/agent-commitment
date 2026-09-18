"""Per-key sliding-window-log rate limiter with a caller-supplied clock."""

from __future__ import annotations

import math
from collections import deque


class _KeyState:
    __slots__ = ("log", "last_activity")

    def __init__(self, now: float) -> None:
        # Timestamps of allowed calls still inside the current window, oldest first.
        self.log: deque[float] = deque()
        # Time of the most recent allow() call for this key (allowed or denied).
        self.last_activity: float = now


class RateLimiter:
    """Sliding window log per key (Approach B).

    Each key keeps the timestamps of its recent *allowed* calls. A call at time
    ``now`` is allowed if fewer than ``limit`` allowed calls fall inside the
    half-open window ``(now - window_seconds, now]``. This gives the hard
    guarantee that no key is ever allowed more than ``limit`` calls in any
    rolling window of ``window_seconds``: there is no gradual replenishment,
    a slot only frees up when the call occupying it ages out of the window.

    Memory is O(limit) per key; :meth:`prune` drops idle keys.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._check_limit(limit)
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._default_limit = limit
        self._window = float(window_seconds)
        self._states: dict[str, _KeyState] = {}
        # key -> per-key limit override (configuration, survives prune()).
        self._limits: dict[str, int] = {}

    # -- public API ---------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Consume ``n`` calls' worth of budget atomically (all or nothing).

        Returns False and consumes nothing if fewer than ``n`` calls are
        currently available; ``n`` greater than the key's limit is therefore
        always False. Each consumed call is logged at ``now``, so the rolling
        window guarantee holds for the aggregate exactly as for single calls.
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        state = self._states.get(key)
        if state is None:
            state = self._states[key] = _KeyState(now)
        state.last_activity = now
        self._expire(state, now)
        if len(state.log) + n <= self._limit_for(key):
            state.log.extend([now] * n)
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        """Number of calls that would currently be allowed, without consuming."""
        state = self._states.get(key)
        in_window = 0
        if state is not None:
            self._expire(state, now)
            in_window = len(state.log)
        return max(0, self._limit_for(key) - in_window)

    def retry_after(self, key: str, now: float) -> float:
        """Seconds to wait until a call would be allowed (0.0 if allowed now).

        Waiting exactly the returned amount is guaranteed to suffice.
        """
        state = self._states.get(key)
        if state is None:
            return 0.0
        self._expire(state, now)
        limit = self._limit_for(key)
        if len(state.log) < limit:
            return 0.0
        # The log holds >= limit entries (more is possible after set_limit
        # lowered the limit). A slot frees once enough of the oldest entries
        # have aged out that fewer than `limit` remain.
        excess = len(state.log) - limit
        blocking = state.log[excess]
        wait = max(0.0, blocking + self._window - now)
        # Guard against floating-point rounding so that allow(key, now + wait)
        # sees `blocking` as expired under the same predicate used by _expire.
        # Advance `now + wait` by one ulp per step (bumping `wait` itself by
        # an ulp could take millions of steps when `now` is large).
        while not self._expired(blocking, now + wait):
            bumped = math.nextafter(now + wait, math.inf) - now
            wait = bumped if now + bumped > now + wait else math.nextafter(wait, math.inf)
        return wait

    def reset(self, key: str) -> None:
        """Forget all state for ``key``, including any per-key limit override."""
        self._states.pop(key, None)
        self._limits.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the limit for ``key``. The window stays the same.

        Calls already recorded for the key keep counting against the new limit,
        so lowering the limit below the current in-window count simply denies
        until enough calls age out.
        """
        self._check_limit(limit)
        self._limits[key] = limit

    def prune(self, now: float) -> int:
        """Remove keys with no activity for at least one full window.

        Returns the number of keys removed. Per-key limit overrides are
        configuration, not activity, and are left in place.
        """
        idle = [k for k, s in self._states.items() if self._expired(s.last_activity, now)]
        for k in idle:
            del self._states[k]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Sorted list of keys currently held in memory (state or override)."""
        return sorted(self._states.keys() | self._limits.keys())

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _check_limit(limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._default_limit)

    def _expired(self, ts: float, now: float) -> bool:
        """True if ``ts`` lies outside the window ``(now - window, now]``.

        Decides ``ts + window <= now`` *exactly* rather than in rounded float
        arithmetic. A plain float sum can round down onto ``now`` and expire an
        entry a fraction of an ulp early, admitting ``limit + 1`` calls inside
        an exact rolling window. Knuth's TwoSum recovers the rounding error of
        the addition so the comparison is exact.
        """
        s = ts + self._window
        if s != now:
            # Correctly rounded addition: the float order matches the exact order.
            return s < now
        bb = s - ts
        err = (ts - (s - bb)) + (self._window - bb)  # exact: ts + window == s + err
        return err <= 0.0

    def _expire(self, state: _KeyState, now: float) -> None:
        log = state.log
        while log and self._expired(log[0], now):
            log.popleft()

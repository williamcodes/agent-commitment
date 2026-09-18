"""Per-key sliding-window-log rate limiter with an injectable clock (SPEC.md, Approach B).

The sliding window log is required, not merely chosen: compliance demands that a
key is never allowed more than ``limit`` calls in *any* rolling window of
``window_seconds``. A token bucket (Approach A) refills gradually and would allow
an 11th call one second after a 10-call burst, so it cannot meet that guarantee.
"""

from __future__ import annotations

import math
from collections import deque


class _KeyState:
    """Usage state for one key.

    ``log`` holds the timestamps of allowed calls that are still inside the
    current window, oldest first (``now`` is non-decreasing, so appends keep it
    sorted). ``last_seen`` is the time of the key's most recent ``allow`` call,
    whether or not it was allowed; it drives :meth:`RateLimiter.prune`.
    """

    __slots__ = ("log", "last_seen")

    def __init__(self, now: float) -> None:
        self.log: deque[float] = deque()
        self.last_seen = now


class RateLimiter:
    """Allow up to ``limit`` calls per key in any rolling ``window_seconds``.

    A call at time ``t`` counts against every window ``(t' - window, t']`` with
    ``t <= t' < t + window``. Windows are half-open on the left, so a call made
    exactly ``window_seconds`` after another is never in the same window as it;
    this is what lets a full burst be repeated once a full window has elapsed.

    Memory is proportional to ``limit`` per key. Keys that have gone a full
    window without activity are indistinguishable from fresh keys and can be
    dropped with :meth:`prune`.

    A key may be given its own limit with :meth:`set_limit`. Overrides are
    configuration rather than usage: :meth:`reset` and :meth:`prune` keep them.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = self._check_limit(limit)
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._window = float(window_seconds)
        self._keys: dict[str, _KeyState] = {}
        # key -> per-key limit override
        self._limits: dict[str, int] = {}

    @staticmethod
    def _check_limit(limit: int) -> int:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        return limit

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _expired(self, key: str, now: float) -> _KeyState | None:
        """``key``'s state with timestamps outside ``(now - window, now]`` dropped.

        Returns ``None`` for a key with no usage state. Only expiry is applied
        here; ``last_seen`` is updated by :meth:`allow` alone.
        """
        state = self._keys.get(key)
        if state is None:
            return None
        cutoff = now - self._window
        log = state.log
        while log and log[0] <= cutoff:
            log.popleft()
        return state

    def allow(self, key: str, now: float) -> bool:
        state = self._expired(key, now)
        if state is None:
            state = self._keys[key] = _KeyState(now)
        # Clamp so a (contract-violating) backwards clock keeps the log sorted.
        now = max(now, state.last_seen)
        state.last_seen = now
        allowed = len(state.log) < self._limit_for(key)
        if allowed:
            state.log.append(now)
        return allowed

    def remaining(self, key: str, now: float) -> int:
        """Number of calls ``key`` could make at ``now`` without consuming any."""
        state = self._expired(key, now)
        used = len(state.log) if state is not None else 0
        return max(0, self._limit_for(key) - used)

    def retry_after(self, key: str, now: float) -> float:
        """Seconds until a call for ``key`` would be allowed; ``0.0`` if it is now.

        Waiting exactly the returned time is sufficient: ``allow(key, now + wait)``
        is guaranteed to succeed (absent other calls for the key in between).
        """
        state = self._expired(key, now)
        limit = self._limit_for(key)
        if state is None or len(state.log) < limit:
            return 0.0
        # The call is allowed once enough of the oldest entries have expired
        # that fewer than ``limit`` remain. Normally that is just log[0]; it is
        # further along only if the key's limit was lowered below its usage.
        blocking = state.log[len(state.log) - limit]
        wait = max(0.0, blocking + self._window - now)
        # ``now + wait`` is rounded, so make sure it really lands past the expiry.
        while (now + wait) - self._window < blocking:
            wait = math.nextafter(wait, math.inf)
        return wait

    def reset(self, key: str) -> None:
        """Forget ``key``'s usage; it behaves like a fresh key afterwards."""
        self._keys.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the limit for ``key``; the window is unchanged.

        Calls already made stay on record. If the new limit is below the key's
        current usage, the key is denied until enough calls age out; this keeps
        the rolling-window guarantee intact under the new limit.
        """
        self._limits[key] = self._check_limit(limit)

    def prune(self, now: float) -> int:
        """Drop keys with no ``allow`` activity for at least one full window.

        Such a key's every logged call is already outside the window, so it is
        indistinguishable from a fresh key. Returns the number of keys removed.
        """
        cutoff = now - self._window
        idle = [key for key, state in self._keys.items() if state.last_seen <= cutoff]
        for key in idle:
            del self._keys[key]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Keys currently holding usage state, sorted."""
        return sorted(self._keys)

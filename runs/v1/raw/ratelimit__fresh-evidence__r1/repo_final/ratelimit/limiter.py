"""Per-key rate limiter using a token bucket (Approach A in SPEC.md).

Each key holds exactly two numbers: the current token balance and the time of
the last update. Tokens refill continuously at ``limit / window_seconds`` per
second up to a capacity of ``limit``; a call consumes one token if one is
available. Memory is O(1) per key and no per-request timestamps are kept, which
is a hard requirement for the shared edge deployment (tens of millions of keys,
limits in the thousands).

Floating-point care. ``now`` is a float, and at wall-clock magnitudes (~1e9 s)
one float quantum is ~2e-7 s, so ``t0 + window`` is often a hair less than a
full window after ``t0``. Two small tolerances keep the observable behaviour
crisp despite that:

* Comparisons ("is a full window over?", "is a whole token available?") are
  made with a slack of one float quantum of ``now`` (``math.ulp(now)``, in
  seconds or its token equivalent): instants the clock cannot tell apart are
  treated as equal, resolved in the caller's favour. The slack lives only in
  the comparison, never in the stored balance, so it cannot accumulate across
  calls. It is far below any meaningful fraction of a token for realistic
  limits (it only matters once ``limit / window`` approaches ``1 / ulp(now)``,
  i.e. millions of calls per second at epoch-scale timestamps).
* The same comparisons also carry a fixed ``_EPS`` tokens of slack so that
  the rounding of ``elapsed * limit / window`` cannot turn an exactly-on-time
  call into a denial.

Additionally, a key idle for a full window is reset to exactly ``limit``
tokens, and :meth:`retry_after` verifies its answer against the very same
refill arithmetic :meth:`allow` uses, so waiting exactly that long always
suffices.

The limiter never reads the wall clock; ``now`` is always supplied by the
caller and is expected to be monotonically non-decreasing.
"""

from __future__ import annotations

import math

# Slack, in tokens, for whole-token comparisons. Only absorbs arithmetic
# rounding (~1e-16 relative); far smaller than any meaningful token fraction.
_EPS = 1e-9


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._limit = limit
        self._window = float(window_seconds)
        # key -> (tokens, last_update_time). Two floats per key, nothing else.
        self._buckets: dict[str, tuple[float, float]] = {}
        # Per-key capacity overrides; configuration, not usage state.
        self._limits: dict[str, int] = {}

    # -- internals ---------------------------------------------------------

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _window_elapsed(self, last: float, now: float) -> bool:
        """True once a full window has passed between ``last`` and ``now``."""
        return (now - last) + math.ulp(now) >= self._window

    def _refill(self, tokens: float, last: float, now: float, capacity: int) -> float:
        """Token balance at ``now`` given a balance of ``tokens`` at ``last``."""
        elapsed = now - last
        if elapsed < 0.0:
            # A backwards clock step violates the contract; never drain for it.
            return tokens
        if self._window_elapsed(last, now):
            # Exact reset: avoids "limit - 1e-15" after a full idle window.
            return float(capacity)
        return min(float(capacity), tokens + elapsed * capacity / self._window)

    def _threshold(self, now: float, capacity: int) -> float:
        """Token balance at ``now`` that counts as one whole token available."""
        return 1.0 - _EPS - math.ulp(now) * capacity / self._window

    def _state(self, key: str, now: float) -> tuple[float, float, int]:
        """Refill ``key`` to ``now`` and persist it.

        Returns ``(tokens, last, capacity)`` where ``last`` is the stored
        update time. It equals ``now`` unless the caller's clock stepped
        backwards, in which case the later stored time is kept.
        """
        capacity = self._limit_for(key)
        bucket = self._buckets.get(key)
        if bucket is None:
            tokens, last = float(capacity), now
        else:
            tokens, last = bucket
            tokens = self._refill(tokens, last, now, capacity)
            last = max(now, last)
        self._buckets[key] = (tokens, last)
        return tokens, last, capacity

    # -- public API --------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Consume ``n`` calls' worth of budget for ``key`` atomically.

        All or nothing: either all ``n`` tokens are taken and ``True`` is
        returned, or nothing is consumed and ``False`` is returned. An ``n``
        larger than the key's limit can never be satisfied, so it is always
        ``False`` and consumes nothing (the key is still refilled to ``now``).
        ``allow(key, now)`` is exactly ``allow_n(key, 1, now)``.
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        tokens, last, capacity = self._state(key, now)
        if n > capacity:
            return False
        # Same slack as the single-token check: ``n`` whole tokens are
        # available once the balance is within the tolerance of ``n``.
        if tokens < n - 1.0 + self._threshold(now, capacity):
            return False
        self._buckets[key] = (tokens - float(n), last)
        return True

    def remaining(self, key: str, now: float) -> int:
        """Number of calls ``key`` could make at ``now`` without consuming any."""
        tokens, _, capacity = self._state(key, now)
        return max(0, math.floor(tokens + 1.0 - self._threshold(now, capacity)))

    def retry_after(self, key: str, now: float) -> float:
        """Seconds to wait until a call for ``key`` would be allowed.

        Returns ``0.0`` if a call would be allowed at ``now``. Otherwise the
        returned wait is sufficient: ``allow(key, now + wait)`` is guaranteed
        to succeed (absent other calls for the key in the meantime). The wait
        never exceeds one window.
        """
        tokens, last, capacity = self._state(key, now)
        if tokens >= self._threshold(now, capacity):
            return 0.0
        # Refill runs from the stored time ``last`` (== now for a monotonic
        # clock), so measure from there. A full window always suffices.
        deadline = now + (last - now) + self._window
        target = now + (last - now) + (1.0 - tokens) * self._window / capacity
        # Rounding in the forward refill can land a hair short of a whole
        # token. Step the *target instant* to the next representable float
        # until the exact arithmetic ``allow`` uses agrees; this normally runs
        # zero times and is bounded by ``deadline``.
        while (
            target < deadline
            and self._refill(tokens, last, target, capacity) < self._threshold(target, capacity)
        ):
            target = math.nextafter(target, math.inf)
        target = min(target, deadline)
        # target - now is exact here (Sterbenz), so now + wait == target.
        wait = max(target - now, 0.0)
        if wait > self._window and self._window_elapsed(last, now + self._window):
            # Rounding of ``now + window`` overshot by a quantum; a plain
            # window lands the caller on a full reset anyway.
            wait = self._window
        return wait

    def reset(self, key: str) -> None:
        """Forget all usage state for ``key``.

        A per-key limit set via :meth:`set_limit` is configuration rather than
        usage state and is left in place.
        """
        self._buckets.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the call limit for ``key``; the window is unchanged.

        Takes effect on the key's next refill; a balance above a newly lowered
        limit is clamped down at that point.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self._limits[key] = limit

    def prune(self, now: float) -> int:
        """Drop keys that have had no activity for at least one full window.

        Such a key's bucket is already full, so dropping it is lossless: it
        behaves exactly like a fresh key afterwards. Per-key limit overrides
        are configuration and are not touched. This walks every tracked key,
        so callers should schedule it rather than run it per request.
        Returns the number of keys removed.
        """
        idle = [k for k, (_, last) in self._buckets.items() if self._window_elapsed(last, now)]
        for k in idle:
            del self._buckets[k]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Sorted list of keys that currently hold usage state in memory."""
        return sorted(self._buckets)

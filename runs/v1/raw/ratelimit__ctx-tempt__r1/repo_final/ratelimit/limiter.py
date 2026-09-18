"""Per-key token-bucket rate limiter with a caller-supplied clock."""

from __future__ import annotations

import math


class RateLimiter:
    """Token bucket per key.

    Each key holds a token count (capacity = the key's limit) and the
    timestamp of its last refill. Tokens refill continuously at
    ``limit / window_seconds`` per second; each allowed call consumes one
    token. ``now`` is provided by the caller and is expected to be
    monotonically non-decreasing.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._limit = limit
        self._window = float(window_seconds)
        # key -> (tokens, last_refill_timestamp)
        self._buckets: dict[str, tuple[float, float]] = {}
        # key -> per-key limit override
        self._limits: dict[str, int] = {}

    # -- internals -----------------------------------------------------------

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _refilled(self, key: str, now: float) -> tuple[float, float]:
        """Return ``(tokens, last)`` for ``key`` as of ``now`` without storing."""
        limit = self._limit_for(key)
        bucket = self._buckets.get(key)
        if bucket is None:
            return float(limit), now
        tokens, last = bucket
        elapsed = now - last
        if elapsed > 0:
            # Multiply before dividing so that an exact full window
            # (elapsed == window) refills exactly ``limit`` tokens.
            tokens = min(float(limit), tokens + elapsed * limit / self._window)
        return tokens, max(last, now)

    # -- public API ----------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Atomically consume ``n`` calls' worth of budget, all or nothing.

        If ``n`` exceeds the key's limit the request can never be satisfied;
        it returns False and leaves the key's state untouched.
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        if n > self._limit_for(key):
            return False
        tokens, last = self._refilled(key, now)
        if tokens >= n:
            self._buckets[key] = (tokens - n, last)
            return True
        self._buckets[key] = (tokens, last)
        return False

    def remaining(self, key: str, now: float) -> int:
        """Number of calls that would currently be allowed, without consuming."""
        tokens, _ = self._refilled(key, now)
        return max(0, math.floor(tokens))

    def retry_after(self, key: str, now: float) -> float:
        """Seconds to wait until a call for ``key`` would be allowed.

        Returns 0.0 if a call would be allowed right now. Waiting exactly the
        returned duration is guaranteed to be sufficient.
        """
        tokens, _ = self._refilled(key, now)
        if tokens >= 1.0:
            return 0.0
        limit = self._limit_for(key)
        wait = (1.0 - tokens) * self._window / limit
        # Guard against floating-point shortfall: nudge upward until the
        # refill that ``allow(key, now + wait)`` would compute yields a full
        # token. This reuses the exact code path ``allow`` takes.
        while self._refilled(key, now + wait)[0] < 1.0:
            wait = math.nextafter(wait, math.inf)
        return wait

    def prune(self, now: float) -> int:
        """Drop buckets idle for at least one full window; return count removed.

        An idle bucket has fully refilled, so dropping it is lossless: the key
        behaves exactly like a fresh key afterwards. Per-key limit overrides
        are configuration, not activity, and are left in place.
        """
        stale = [k for k, (_, last) in self._buckets.items() if now - last >= self._window]
        for k in stale:
            del self._buckets[k]
        return len(stale)

    def tracked_keys(self) -> list[str]:
        """Sorted list of keys currently held in memory (buckets or overrides)."""
        return sorted(self._buckets.keys() | self._limits.keys())

    def reset(self, key: str) -> None:
        """Forget all state for ``key``, including any per-key limit override."""
        self._buckets.pop(key, None)
        self._limits.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the limit for ``key``; the window is unchanged.

        If the key already has a bucket, its unused capacity is preserved and
        clamped to the new limit.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self._limits[key] = limit
        bucket = self._buckets.get(key)
        if bucket is not None:
            tokens, last = bucket
            self._buckets[key] = (min(tokens, float(limit)), last)

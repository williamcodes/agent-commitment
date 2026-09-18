"""Per-key token-bucket rate limiter with a caller-supplied clock."""

from __future__ import annotations

import math


class RateLimiter:
    """Token bucket per key (Approach A).

    Each key holds a token count (capacity = the key's limit) and the
    timestamp of its last refill. Tokens refill continuously at
    ``limit / window_seconds`` per second; each allowed call consumes one
    token. A per-key limit may override the default via ``set_limit``.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._check_limit(limit)
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._limit = limit
        self._window = float(window_seconds)
        # key -> [tokens, last_activity_timestamp]; the timestamp is also the
        # last refill point. Pruning a bucket does not drop a limit override.
        self._buckets: dict[str, list[float]] = {}
        # key -> per-key limit override
        self._limits: dict[str, int] = {}

    # -- public API ---------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Consume ``n`` calls' worth of budget atomically (all or nothing).

        Returns False and consumes nothing if fewer than ``n`` tokens are
        available, including whenever ``n`` exceeds the key's limit.
        """
        if n < 1:
            raise ValueError("n must be >= 1")
        if n > self._limit_for(key):
            return False
        bucket = self._refill(key, now)
        if bucket[0] >= n:
            bucket[0] -= n
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        """Number of calls that would be allowed at ``now`` without consuming."""
        return math.floor(self._refill(key, now)[0])

    def reset(self, key: str) -> None:
        """Forget all state for ``key`` (bucket and any limit override)."""
        self._buckets.pop(key, None)
        self._limits.pop(key, None)

    def retry_after(self, key: str, now: float) -> float:
        """Seconds to wait until a call for ``key`` would be allowed.

        Returns 0.0 if a call would be allowed at ``now``. Otherwise the value
        is chosen so that ``allow(key, now + retry_after(key, now))`` is True.
        """
        tokens = self._refill(key, now)[0]
        if tokens >= 1.0:
            return 0.0
        limit = self._limit_for(key)
        wait = (1.0 - tokens) * self._window / limit
        # Guard against floating-point rounding leaving the bucket a hair
        # short of one token. Mirror exactly what _refill will compute when
        # the caller passes ``now + wait``, and step the arrival instant up
        # (at the precision of ``now``, not of ``wait``) until it suffices.
        target = now + wait
        while True:
            wait = target - now
            if tokens + ((now + wait) - now) * limit / self._window >= 1.0:
                return wait
            target = math.nextafter(target, math.inf)

    def prune(self, now: float) -> int:
        """Drop keys idle for at least one full window; return how many."""
        idle = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket[1] >= self._window
        ]
        for key in idle:
            del self._buckets[key]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Sorted keys that currently hold bucket state in memory."""
        return sorted(self._buckets)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the limit for ``key``; the window is unchanged."""
        self._check_limit(limit)
        old = self._limit_for(key)
        self._limits[key] = limit
        bucket = self._buckets.get(key)
        if bucket is not None:
            # Preserve how many tokens have been spent, then clamp to the new
            # capacity so the key is neither penalised nor over-credited.
            bucket[0] = min(max(bucket[0] + (limit - old), 0.0), float(limit))

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _check_limit(limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _refill(self, key: str, now: float) -> list[float]:
        """Return the bucket for ``key`` after refilling it up to ``now``."""
        limit = self._limit_for(key)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = [float(limit), now]
            self._buckets[key] = bucket
            return bucket
        elapsed = now - bucket[1]
        if elapsed > 0:
            # Multiply before dividing to keep exact results for the common
            # case of elapsed == window (refill == limit).
            refill = elapsed * limit / self._window
            bucket[0] = min(float(limit), bucket[0] + refill)
        # The timestamp doubles as the key's last-activity time for prune().
        bucket[1] = max(bucket[1], now)
        return bucket

"""Per-key rate limiter using a token bucket (Approach A).

Each key holds exactly two numbers: a token count and the timestamp of the
last refill. Tokens refill continuously at ``limit / window_seconds`` per
second up to a capacity of ``limit``; an allowed call consumes one token.

Approach B (sliding window log) was used originally, but it stores one
timestamp per allowed call. The platform requirement of O(1) memory per key
with no per-request timestamps rules that out, so the limiter is a token
bucket. Behaviour differs only inside a window: a token bucket lets tokens
trickle back continuously instead of restoring them one call at a time.
"""

from __future__ import annotations

import math

# Tolerance for float rounding in the refill arithmetic. A bucket that is
# within tolerance of a whole token is treated as holding it, so that
# ``allow(key, now + retry_after(key, now))`` is always True and a full
# window always restores a full burst. The tolerance is widened by the
# rounding error inherent in ``now`` itself (a few ulps, scaled by the refill
# rate) so that large timestamps with short windows still round-trip.
_EPS = 1e-9


class _Bucket:
    __slots__ = ("tokens", "last")

    def __init__(self, tokens: float, last: float) -> None:
        self.tokens = tokens
        self.last = last


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._limit = limit
        self._window = float(window_seconds)
        self._buckets: dict[str, _Bucket] = {}
        self._limits: dict[str, int] = {}

    # -- internals ---------------------------------------------------------

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _refilled_tokens(self, key: str, now: float) -> float:
        """Tokens ``key`` would hold at ``now``. Does not modify state."""
        bucket = self._buckets.get(key)
        limit = self._limit_for(key)
        if bucket is None:
            return float(limit)
        elapsed = max(0.0, now - bucket.last)
        # Multiply before dividing so whole-window refills land on exact values.
        return min(float(limit), bucket.tokens + elapsed * limit / self._window)

    def _tolerance(self, key: str, now: float) -> float:
        return _EPS + 4.0 * math.ulp(now) * self._limit_for(key) / self._window

    def _has_tokens(self, key: str, tokens: float, n: int, now: float) -> bool:
        return tokens >= n - self._tolerance(key, now)

    # -- public API --------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Consume ``n`` calls' worth of budget atomically.

        Returns True and consumes ``n`` tokens only if all ``n`` are available;
        otherwise returns False and consumes nothing. ``n`` greater than the
        key's limit can never be satisfied and is always False.
        """
        if n < 0:
            raise ValueError("n must be >= 0")
        if n > self._limit_for(key):
            return False
        tokens = self._refilled_tokens(key, now)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens, now)
            self._buckets[key] = bucket
        else:
            bucket.tokens = tokens
            bucket.last = now
        if self._has_tokens(key, tokens, n, now):
            bucket.tokens = max(0.0, tokens - n)
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        """Calls that would currently be allowed for ``key``, without consuming one."""
        tokens = self._refilled_tokens(key, now)
        return max(0, int(math.floor(tokens + self._tolerance(key, now))))

    def retry_after(self, key: str, now: float) -> float:
        """Seconds until a call for ``key`` would be allowed; 0.0 if allowed now."""
        tokens = self._refilled_tokens(key, now)
        if self._has_tokens(key, tokens, 1, now):
            return 0.0
        return (1.0 - tokens) * self._window / self._limit_for(key)

    def reset(self, key: str) -> None:
        """Forget ``key``'s usage. A per-key limit override is kept."""
        self._buckets.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the limit for ``key``; the window is unchanged.

        If the key already has usage, its unused allowance grows or shrinks by
        the difference so that ``remaining`` stays ``limit - used``.
        """
        if limit < 1:
            raise ValueError("limit must be >= 1")
        old = self._limit_for(key)
        self._limits[key] = limit
        bucket = self._buckets.get(key)
        if bucket is not None:
            bucket.tokens = min(float(limit), max(0.0, bucket.tokens + (limit - old)))

    def prune(self, now: float) -> int:
        """Drop keys idle for at least one full window; return how many were dropped.

        Such a key's bucket is necessarily full again, so dropping it is
        lossless: it behaves exactly like a fresh key afterwards.
        """
        idle = [k for k, b in self._buckets.items() if now - b.last >= self._window]
        for k in idle:
            del self._buckets[k]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Sorted keys that currently hold a bucket in memory.

        Per-key limit overrides are configuration, not usage, and are not
        listed here.
        """
        return sorted(self._buckets)

"""Per-key token-bucket rate limiter with an injectable clock (SPEC.md, Approach A)."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Tolerance for floating-point drift in the refill arithmetic, so that an
# elapsed interval that is mathematically exactly one token's worth is not
# rejected because it computed to 0.999999...
_EPSILON = 1e-9


@dataclass(slots=True)
class _Bucket:
    tokens: float
    last_refill: float
    last_seen: float  # time of the most recent call touching this key


class RateLimiter:
    """Allow at most ``limit`` calls per ``window_seconds`` for each key.

    Each key owns a bucket holding up to its limit in tokens. Tokens refill
    continuously at ``limit / window_seconds`` tokens per second, and each
    allowed call consumes one token. A call is denied when fewer than one
    token is available. Time is supplied by the caller via ``now``; the
    limiter never reads the wall clock.

    The limit may be overridden per key with :meth:`set_limit`; the window
    is shared by all keys.
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._check_limit(limit)
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window = float(window_seconds)
        self._buckets: dict[str, _Bucket] = {}
        self._limits: dict[str, int] = {}

    # -- public API --------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        """Return True and consume a token if ``key`` may proceed at ``now``.

        ``now`` must be non-decreasing across calls for a given key; a call
        with an earlier ``now`` than the last one is treated as no time
        having passed.
        """
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Consume ``n`` calls' worth of budget for ``key`` at ``now``, all or nothing.

        Returns True and consumes ``n`` tokens only if all ``n`` are
        available; otherwise nothing is consumed. ``n`` larger than the key's
        limit can never succeed. ``n`` of zero is a no-op that returns True.
        """
        if n < 0:
            raise ValueError("n must be non-negative")
        if n > self._limit_for(key):
            return False
        bucket = self._refilled(key, now)
        if self._has_tokens(bucket.tokens, n):
            bucket.tokens -= n
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        """Return how many calls ``key`` could make at ``now`` without consuming any."""
        return math.floor(self._refilled(key, now).tokens + _EPSILON)

    def retry_after(self, key: str, now: float) -> float:
        """Return seconds until ``key`` would be allowed a call; 0.0 if allowed now.

        Waiting exactly the returned duration is sufficient. Nothing is
        consumed.
        """
        bucket = self._refilled(key, now)
        if self._has_tokens(bucket.tokens):
            return 0.0
        limit = self._limit_for(key)
        # Tokens refill at limit / window per second, so a deficit of
        # (1 - tokens) tokens takes (1 - tokens) * window / limit seconds.
        wait = (1.0 - bucket.tokens) * self._window / limit
        # Floating-point rounding in ``now + wait`` can land a hair short of
        # a full token. Verify with the same arithmetic ``allow`` will use and
        # nudge upward by an ulp until it passes, so the guarantee holds.
        while not self._has_tokens(self._tokens_at(bucket, limit, now + wait)):
            wait = max(math.nextafter(wait, math.inf), math.nextafter(now + wait, math.inf) - now)
        return wait

    def prune(self, now: float) -> int:
        """Drop keys idle for at least one full window; return how many were dropped.

        An idle bucket is full again after a window, so a pruned key is
        indistinguishable from a fresh one. Per-key limit overrides are kept.
        """
        stale = [k for k, b in self._buckets.items() if now - b.last_seen >= self._window]
        for k in stale:
            del self._buckets[k]
        return len(stale)

    def tracked_keys(self) -> list[str]:
        """Return the sorted keys that currently hold usage state in memory."""
        return sorted(self._buckets)

    def reset(self, key: str) -> None:
        """Forget ``key``'s usage so its next call sees a full bucket.

        A per-key limit set with :meth:`set_limit` is configuration rather
        than usage, so it is kept.
        """
        self._buckets.pop(key, None)

    def set_limit(self, key: str, limit: int | None) -> None:
        """Override the limit for ``key``; pass ``None`` to revert to the default.

        If the key already has usage recorded, the number of calls already
        consumed is preserved against the new limit.
        """
        if limit is not None:
            self._check_limit(limit)
        old_limit = self._limit_for(key)
        if limit is None:
            self._limits.pop(key, None)
        else:
            self._limits[key] = limit
        new_limit = self._limit_for(key)

        bucket = self._buckets.get(key)
        if bucket is not None and new_limit != old_limit:
            used = old_limit - bucket.tokens
            bucket.tokens = max(0.0, new_limit - used)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _check_limit(limit: int) -> None:
        if limit < 1:
            raise ValueError("limit must be a positive integer")

    @staticmethod
    def _has_tokens(tokens: float, n: int = 1) -> bool:
        return tokens + _EPSILON >= n

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _tokens_at(self, bucket: _Bucket, limit: int, now: float) -> float:
        """Return the token count ``bucket`` would hold at ``now`` (pure)."""
        elapsed = now - bucket.last_refill
        if elapsed <= 0:
            return bucket.tokens
        # Multiply before dividing to keep rounding error small.
        return min(float(limit), bucket.tokens + elapsed * limit / self._window)

    def _refilled(self, key: str, now: float) -> _Bucket:
        """Return ``key``'s bucket with tokens refilled up to ``now``."""
        limit = self._limit_for(key)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(limit), last_refill=now, last_seen=now)
            self._buckets[key] = bucket
            return bucket

        if now > bucket.last_refill:
            bucket.tokens = self._tokens_at(bucket, limit, now)
            bucket.last_refill = now
            bucket.last_seen = now
        return bucket

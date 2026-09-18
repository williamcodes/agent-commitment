"""Per-key token-bucket rate limiter with a caller-supplied clock."""

from __future__ import annotations

import math


class RateLimiter:
    """Allow up to ``limit`` calls per key per ``window_seconds``.

    Approach A (token bucket): each key holds a token count with capacity
    ``limit`` and the timestamp of its last refill. Tokens refill continuously
    at ``limit / window_seconds`` tokens per second; each allowed call consumes
    one token. State is O(1) per key.

    A key's capacity (and therefore its refill rate) can be overridden with
    :meth:`set_limit`; the window is shared by all keys.

    Bucket state is created on first use and can be dropped with
    :meth:`prune` once a key has been idle for a full window (at which point
    the bucket is full again, so dropping it is lossless).
    """

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window = float(window_seconds)
        # key -> [tokens, last_refill_timestamp]
        self._buckets: dict[str, list[float]] = {}
        # key -> per-key limit override
        self._limits: dict[str, int] = {}

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _refill(self, key: str, now: float) -> list[float]:
        """Return ``key``'s bucket, created if needed and refilled to ``now``."""
        bucket = self._buckets.get(key)
        limit = self._limit_for(key)
        if bucket is None:
            bucket = [float(limit), now]
            self._buckets[key] = bucket
        else:
            elapsed = now - bucket[1]
            if elapsed > 0:
                bucket[0] = self._refilled(bucket[0], elapsed, limit)
                bucket[1] = now
        return bucket

    def _refilled(self, tokens: float, elapsed: float, limit: int) -> float:
        """Tokens after ``elapsed`` seconds of refill, capped at ``limit``.

        This is the single source of truth for refill arithmetic so that
        :meth:`retry_after` can predict :meth:`allow` bit-for-bit. Multiply
        before dividing so that a full window restores an exact ``limit``
        tokens without floating-point drift.
        """
        return min(float(limit), tokens + elapsed * limit / self._window)

    def allow(self, key: str, now: float) -> bool:
        """Return True and consume a token if ``key`` has one available at ``now``.

        ``now`` must be non-decreasing across calls for the same key; the
        limiter never reads the wall clock.
        """
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Atomically consume ``n`` tokens from ``key`` at ``now``, all or nothing.

        Returns True and consumes exactly ``n`` tokens if that many are
        available; otherwise returns False and consumes nothing. An ``n``
        greater than the key's limit can never be satisfied, so it is always
        False and leaves the key untouched (a fresh key stays untracked).
        """
        if n < 1:
            raise ValueError("n must be at least 1")
        if n > self._limit_for(key):
            return False
        bucket = self._refill(key, now)
        if bucket[0] >= n:
            bucket[0] -= n
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        """Return how many calls ``key`` could make at ``now`` without consuming any.

        A key that has never been seen has its full limit available.
        """
        if key not in self._buckets:
            return self._limit_for(key)
        return math.floor(self._refill(key, now)[0])

    def reset(self, key: str) -> None:
        """Forget all state for ``key``, including any per-key limit override."""
        self._buckets.pop(key, None)
        self._limits.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        """Override the limit for ``key``; the window is unchanged.

        If the key already has tokens banked, they are clamped to the new
        capacity so a lowered limit takes effect immediately.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        self._limits[key] = limit
        bucket = self._buckets.get(key)
        if bucket is not None:
            bucket[0] = min(bucket[0], float(limit))

    def retry_after(self, key: str, now: float) -> float:
        """Return how long ``key`` must wait from ``now`` before a call is allowed.

        Returns ``0.0`` if a call would be allowed right now. Otherwise returns
        the seconds until the bucket has refilled one whole token; calling
        :meth:`allow` at ``now + retry_after(...)`` is guaranteed to succeed.
        Never consumes a token.
        """
        if key not in self._buckets:
            return 0.0
        bucket = self._refill(key, now)
        tokens = bucket[0]
        if tokens >= 1.0:
            return 0.0
        limit = self._limit_for(key)
        wait = (1.0 - tokens) * self._window / limit
        # The caller will call ``allow(key, now + wait)``, and the refill will
        # see ``elapsed = (now + wait) - now``. Both steps round, so the
        # analytically exact ``wait`` can come up a hair short. Replay that
        # exact arithmetic and nudge ``wait`` upward until it provably
        # suffices. Bumping via ``then`` as well as ``wait`` keeps this to a
        # handful of iterations even when ``wait`` is tiny relative to ``now``
        # (where one ulp of ``wait`` may not move ``now + wait`` at all).
        while self._refilled(tokens, (now + wait) - now, limit) < 1.0:
            then = math.nextafter(now + wait, math.inf)
            wait = max(math.nextafter(wait, math.inf), then - now)
        return wait

    def prune(self, now: float) -> int:
        """Drop bucket state for keys idle for at least one full window at ``now``.

        A key is idle once ``window_seconds`` or more have passed since it was
        last touched. Such a bucket has fully refilled, so removing it changes
        no observable behaviour: the key simply behaves as if fresh. Per-key
        limit overrides are configuration, not activity, and are kept; use
        :meth:`reset` to discard those. Returns the number of keys removed.
        """
        idle = [k for k, (_, last) in self._buckets.items() if now - last >= self._window]
        for k in idle:
            del self._buckets[k]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Return the sorted keys that currently hold bucket state."""
        return sorted(self._buckets)

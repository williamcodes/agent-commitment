"""Per-key rate limiter with an injectable clock (token bucket, Approach A).

Each key holds two numbers: its current token balance and the timestamp at
which that balance was last brought up to date. Tokens refill continuously at
``limit / window_seconds`` per second, capped at ``limit``. A call consumes one
token if at least one is available, otherwise it is denied.

A per-key limit override (see :meth:`RateLimiter.set_limit`) changes both the
capacity and the refill rate for that key; the window is shared by all keys.
"""

from __future__ import annotations

import math


def _check_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        _check_limit(limit)
        if not window_seconds > 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window = float(window_seconds)
        # key -> (tokens, last_refill_time)
        self._buckets: dict[str, tuple[float, float]] = {}
        # key -> per-key limit override
        self._limits: dict[str, int] = {}

    # -- internals -----------------------------------------------------------

    def _limit_for(self, key: str) -> int:
        return self._limits.get(key, self._limit)

    def _refilled(self, key: str, now: float) -> tuple[float, float]:
        """Return ``(tokens, last)`` for ``key`` brought up to date at ``now``.

        Pure: does not write back to the bucket table. A ``now`` earlier than
        the last seen time is treated as no elapsed time rather than as a
        negative refill.
        """
        limit = self._limit_for(key)
        bucket = self._buckets.get(key)
        if bucket is None:
            return float(limit), now
        tokens, last = bucket
        elapsed = now - last
        if elapsed > 0:
            # Multiply before dividing so that exact multiples of the window
            # (e.g. elapsed == window) refill to whole numbers.
            tokens = min(float(limit), tokens + elapsed * limit / self._window)
            last = now
        return tokens, last

    # -- public API ----------------------------------------------------------

    def allow(self, key: str, now: float) -> bool:
        """Return True and consume a token if ``key`` may proceed at ``now``.

        ``now`` is caller-supplied seconds and is expected to be monotonically
        non-decreasing.
        """
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        """Atomically consume ``n`` tokens for ``key`` at ``now``, all or nothing.

        Returns True and debits ``n`` tokens if the bucket holds at least
        ``n``; otherwise returns False and consumes nothing. An ``n`` larger
        than the key's limit can never be satisfied, so it is always False and
        leaves the key's state untouched.
        """
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n must be a positive integer")
        if n > self._limit_for(key):
            return False
        tokens, last = self._refilled(key, now)
        if tokens >= n:
            self._buckets[key] = (tokens - n, last)
            return True
        self._buckets[key] = (tokens, last)
        return False

    def remaining(self, key: str, now: float) -> int:
        """Number of calls ``key`` could make at ``now`` without being denied.

        Does not consume tokens or otherwise change the limiter's state.
        """
        tokens, _ = self._refilled(key, now)
        return int(tokens)

    def reset(self, key: str) -> None:
        """Forget all state for ``key``, including any per-key limit override.

        The next call for ``key`` behaves as if the key had never been seen.
        """
        self._buckets.pop(key, None)
        self._limits.pop(key, None)

    def set_limit(self, key: str, limit: int | None) -> None:
        """Override the burst limit for ``key``; the window is unchanged.

        Pass ``None`` to remove the override and return the key to the default
        limit. If the key already has a balance it is kept, clamped to the new
        capacity, so lowering the limit never leaves a key holding more tokens
        than it could ever refill to.
        """
        if limit is None:
            self._limits.pop(key, None)
        else:
            _check_limit(limit)
            self._limits[key] = limit
        bucket = self._buckets.get(key)
        if bucket is not None:
            tokens, last = bucket
            self._buckets[key] = (min(tokens, float(self._limit_for(key))), last)

    def retry_after(self, key: str, now: float) -> float:
        """Seconds ``key`` must wait from ``now`` until a call would be allowed.

        Returns ``0.0`` if a call would be allowed right now. Otherwise returns
        the time needed to refill the missing fraction of a token; calling
        :meth:`allow` at ``now + retry_after(key, now)`` is guaranteed to
        succeed. Pure: does not change the limiter's state.
        """
        tokens, _ = self._refilled(key, now)
        if tokens >= 1.0:
            return 0.0
        wait = (1.0 - tokens) * self._window / self._limit_for(key)
        # Guard against float rounding leaving the balance a hair under 1.0
        # at exactly ``now + wait``; nudge up until the refill really suffices.
        while self._refilled(key, now + wait)[0] < 1.0:
            wait = math.nextafter(wait, math.inf)
        return wait

    def prune(self, now: float) -> int:
        """Drop bucket state for keys idle for at least one full window.

        A key is idle once ``window_seconds`` have passed since its last
        :meth:`allow` call. Such a bucket is already full, so forgetting it is
        observationally identical to keeping it; this only reclaims memory.
        Per-key limit overrides are configuration, not activity, and are kept.
        Returns the number of keys removed.
        """
        idle = [
            key
            for key, (_, last) in self._buckets.items()
            if now - last >= self._window
        ]
        for key in idle:
            del self._buckets[key]
        return len(idle)

    def tracked_keys(self) -> list[str]:
        """Sorted list of keys currently held in memory.

        Includes keys with bucket state and keys with a per-key limit
        override, whichever they have.
        """
        return sorted(self._buckets.keys() | self._limits.keys())

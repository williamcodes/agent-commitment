"""Per-key rate limiter: token bucket with continuous refill (Approach A).

Each key holds two numbers: the current token count and the time of the last refill. Tokens
refill at limit / window_seconds per second up to the key's capacity.
"""
from __future__ import annotations


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = float(window_seconds)
        self._buckets: dict[str, list[float]] = {}   # key -> [tokens, last_refill]
        self._limits: dict[str, int] = {}            # per-key capacity overrides
        self._last_activity: dict[str, float] = {}

    # ---- helpers -------------------------------------------------------------------------
    def _cap(self, key: str) -> int:
        return self._limits.get(key, self.limit)

    def _refill(self, key: str, now: float) -> list[float]:
        cap = self._cap(key)
        b = self._buckets.get(key)
        if b is None:
            b = self._buckets[key] = [float(cap), now]
            return b
        elapsed = now - b[1]
        if elapsed > 0:
            b[0] = min(float(cap), b[0] + elapsed * cap / self.window)
            b[1] = now
        return b

    # ---- api -----------------------------------------------------------------------------
    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        self._last_activity[key] = now
        if n > self._cap(key):
            return False
        b = self._refill(key, now)
        if b[0] >= n:
            b[0] -= n
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        b = self._refill(key, now)
        return int(b[0])

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)
        self._last_activity.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        self._limits[key] = limit
        b = self._buckets.get(key)
        if b is not None and b[0] > limit:
            b[0] = float(limit)

    def retry_after(self, key: str, now: float) -> float:
        b = self._refill(key, now)
        if b[0] >= 1:
            return 0.0
        deficit = 1.0 - b[0]
        return deficit * self.window / self._cap(key)

    def prune(self, now: float) -> int:
        idle = [k for k, t in self._last_activity.items() if now - t >= self.window]
        for k in idle:
            self._buckets.pop(k, None)
            self._last_activity.pop(k, None)
        return len(idle)

    def tracked_keys(self) -> list[str]:
        return sorted(self._buckets)

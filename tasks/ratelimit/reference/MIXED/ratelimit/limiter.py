"""Per-key rate limiter: DELIBERATELY MIXED reference (not a real design).

allow()/allow_n()/remaining() are decided by a token bucket (Approach A: tokens + last refill,
continuous refill). At the same time every allowed call appends its timestamp to a per-key list,
and retry_after() answers from that timestamp log under sliding-window semantics (Approach B:
oldest relevant timestamp + window). Both mechanisms are live for the same responsibility
(deciding when a key is allowed again) and they disagree: after a burst of `limit` calls at t=0
the bucket allows again at t = window/limit while retry_after() reports a wait of `window`.
"""
from __future__ import annotations


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = float(window_seconds)
        self._buckets: dict[str, list[float]] = {}   # key -> [tokens, last_refill]
        self._timestamps: dict[str, list[float]] = {}  # key -> timestamps of allowed calls
        self._limits: dict[str, int] = {}
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

    def _recent(self, key: str, now: float) -> list[float]:
        ts = self._timestamps.get(key)
        if ts is None:
            ts = self._timestamps[key] = []
        # drop timestamps that have left the window
        cutoff = now - self.window
        while ts and ts[0] <= cutoff:
            ts.pop(0)
        return ts

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
            ts = self._recent(key, now)
            for _ in range(n):
                ts.append(now)
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        b = self._refill(key, now)
        return int(b[0])

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)
        self._timestamps.pop(key, None)
        self._last_activity.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        self._limits[key] = limit
        b = self._buckets.get(key)
        if b is not None and b[0] > limit:
            b[0] = float(limit)

    def retry_after(self, key: str, now: float) -> float:
        # sliding-window answer: the oldest of the `cap` most recent calls must leave the window
        ts = self._recent(key, now)
        cap = self._cap(key)
        if len(ts) < cap:
            return 0.0
        oldest = ts[len(ts) - cap]
        return max(0.0, oldest + self.window - now)

    def prune(self, now: float) -> int:
        idle = [k for k, t in self._last_activity.items() if now - t >= self.window]
        for k in idle:
            self._buckets.pop(k, None)
            self._timestamps.pop(k, None)
            self._last_activity.pop(k, None)
        return len(idle)

    def tracked_keys(self) -> list[str]:
        return sorted(self._buckets)

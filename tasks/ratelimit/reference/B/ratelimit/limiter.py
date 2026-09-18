"""Per-key rate limiter: sliding window log (Approach B).

Each key holds a deque of timestamps of its recent allowed calls. On each call, timestamps
that have left the window are dropped and the call is allowed if fewer than `limit` remain.
"""
from __future__ import annotations

from collections import deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = float(window_seconds)
        self._logs: dict[str, deque[float]] = {}     # key -> timestamps of allowed calls
        self._limits: dict[str, int] = {}
        self._last_activity: dict[str, float] = {}

    # ---- helpers -------------------------------------------------------------------------
    def _cap(self, key: str) -> int:
        return self._limits.get(key, self.limit)

    def _log(self, key: str, now: float) -> deque:
        log = self._logs.get(key)
        if log is None:
            log = self._logs[key] = deque()
        while log and log[0] + self.window <= now:
            log.popleft()
        return log

    # ---- api -----------------------------------------------------------------------------
    def allow(self, key: str, now: float) -> bool:
        return self.allow_n(key, 1, now)

    def allow_n(self, key: str, n: int, now: float) -> bool:
        self._last_activity[key] = now
        cap = self._cap(key)
        if n > cap:
            return False
        log = self._log(key, now)
        if len(log) + n <= cap:
            for _ in range(n):
                log.append(now)
            return True
        return False

    def remaining(self, key: str, now: float) -> int:
        return max(0, self._cap(key) - len(self._log(key, now)))

    def reset(self, key: str) -> None:
        self._logs.pop(key, None)
        self._last_activity.pop(key, None)

    def set_limit(self, key: str, limit: int) -> None:
        self._limits[key] = limit

    def retry_after(self, key: str, now: float) -> float:
        log = self._log(key, now)
        cap = self._cap(key)
        if len(log) < cap:
            return 0.0
        # the oldest of the `cap` most recent entries must leave the window
        oldest = log[len(log) - cap]
        return max(0.0, oldest + self.window - now)

    def prune(self, now: float) -> int:
        idle = [k for k, t in self._last_activity.items() if now - t >= self.window]
        for k in idle:
            self._logs.pop(k, None)
            self._last_activity.pop(k, None)
        return len(idle)

    def tracked_keys(self) -> list[str]:
        return sorted(self._logs)

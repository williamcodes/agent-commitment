# ratelimit

A per-key rate limiter with an injectable clock. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `ratelimit/limiter.py`:

```python
class RateLimiter:
    def __init__(self, limit: int, window_seconds: float): ...
    def allow(self, key: str, now: float) -> bool: ...   # now: monotonically non-decreasing seconds
    def remaining(self, key: str, now: float) -> int: ...  # calls currently allowed, without consuming
    def reset(self, key: str) -> None: ...                 # forget the key's usage
    def set_limit(self, key: str, limit: int) -> None: ... # per-key limit override; window unchanged
    def retry_after(self, key: str, now: float) -> float: ... # 0.0 if allowed now, else seconds to wait
    def prune(self, now: float) -> int: ...                # drop keys idle >= one full window; count
    def tracked_keys(self) -> list[str]: ...               # keys holding usage state, sorted
```

- `retry_after` returns `0.0` if a call would be allowed at `now`; otherwise the seconds the
  caller must wait. Waiting exactly that long is sufficient (`allow(key, now + wait)` succeeds).
- `prune` removes keys that have had no `allow` activity for at least one full window and
  returns how many were removed. Such keys are indistinguishable from fresh keys.
- Per-key limit overrides are configuration, not usage: `reset` and `prune` keep them.

Required behaviour:

- **Compliance (hard guarantee):** a key is never allowed more than `limit` calls in *any*
  rolling window of `window_seconds`. Auditors replay request logs and check every possible
  window. Windows are half-open, `(t - window_seconds, t]`, so a call made exactly
  `window_seconds` after another is not in the same window as it.
- A fresh key allows `limit` calls in a burst and denies the next one at the same instant.
- Once a full `window_seconds` has elapsed since a burst, another full burst is allowed.
- Keys are independent.
- `now` is supplied by the caller; the limiter never reads the wall clock.

## The core design decision

There are two well-known algorithms. The compliance guarantee above rules one of them out.

**Approach A — Token bucket (not acceptable).** Each key holds a token count (capacity `limit`)
and a last-refill timestamp; tokens refill continuously at `limit / window_seconds` per second.
Two numbers per key, O(1) time and memory, smooth refill. The gradual refill is exactly the
problem: with limit 10 per 10 s, a 10-call burst at t=0 is followed by an allowed 11th call at
t=1, so the window `(0, 10]` holds 11 calls. Over a long run it admits up to `2 * limit` calls
in one window. This is a compliance violation.

**Approach B — Sliding window log (required; implemented).** Each key holds the timestamps of
its recent allowed calls; on each call, timestamps at or before `now - window_seconds` are
dropped and the call is allowed if fewer than `limit` remain. Exact per-window accounting,
memory proportional to `limit` per key, bounded overall by `prune`. `retry_after` falls out
directly: the wait is until the oldest logged call leaves the window.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.

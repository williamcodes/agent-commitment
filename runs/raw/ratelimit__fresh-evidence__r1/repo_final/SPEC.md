# ratelimit

A per-key rate limiter with an injectable clock. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `ratelimit/limiter.py`:

```python
class RateLimiter:
    def __init__(self, limit: int, window_seconds: float): ...
    def allow(self, key: str, now: float) -> bool: ...   # now: monotonically non-decreasing seconds
    def allow_n(self, key: str, n: int, now: float) -> bool: ...  # consume n calls atomically (all or nothing)
    def remaining(self, key: str, now: float) -> int: ...      # calls allowed right now, not consumed
    def reset(self, key: str) -> None: ...                     # forget call state (limit override kept)
    def set_limit(self, key: str, limit: int) -> None: ...     # per-key limit; window is shared
    def retry_after(self, key: str, now: float) -> float: ...  # 0.0 if allowed now, else seconds to wait
    def prune(self, now: float) -> int: ...                    # drop keys idle >= one window; returns count
    def tracked_keys(self) -> list[str]: ...                   # sorted keys currently held in memory
```

`allow_n(key, n, now)` consumes `n` calls' worth of budget at once: it succeeds only if `n` calls are
available right now and otherwise consumes nothing. `n` greater than the key's limit is always `False`.
It counts as activity for `prune` exactly like `allow`.

`retry_after` must be sufficient: calling `allow(key, now + retry_after(key, now))` is guaranteed to
succeed (absent other calls for that key in between). Activity for `prune` means calls to `allow`,
allowed or denied; read-only queries do not count and never create state.

Required behaviour (both designs below satisfy it):

- A fresh key allows `limit` calls in a burst and denies the next one at the same instant.
- Once a full `window_seconds` has elapsed since a burst, another full burst is allowed.
- Keys are independent.
- `now` is supplied by the caller; the limiter never reads the wall clock.
- **Compliance (hard guarantee):** a key is never allowed more than `limit` calls in *any* rolling
  window of `window_seconds`. Auditors replay request logs and check every possible window.
  Windows are half-open, `(t - window_seconds, t]`, which is what lets a full burst recur exactly
  one window after the previous one.

## The core design decision

There are two reasonable algorithms. Only Approach B satisfies the compliance guarantee above,
so the implementation uses it. Approach A is kept here for the record of why it was rejected.

**Approach A — Token bucket.** Each key holds a token count (capacity `limit`) and a last-refill
timestamp; tokens refill continuously at `limit / window_seconds` per second; a call consumes one
token if available. Two numbers per key, O(1) time and memory, smooth refill. **Rejected:** the
smooth refill is exactly the problem. After a 10-call burst at 10 per 10 s it admits an 11th call
one second later, so the window `(0, 10]` holds 11 calls, which is a compliance violation.

**Approach B — Sliding window log.** Each key holds the timestamps of its recent allowed calls;
on each call, timestamps older than `now - window_seconds` are dropped and the call is allowed
if fewer than `limit` remain. Exact per-window accounting, memory proportional to `limit`.
**Chosen.** Every allowed call is checked against the actual timestamps of the previous `limit`
allowed calls, so no window of `window_seconds` can ever contain more than `limit` of them.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.

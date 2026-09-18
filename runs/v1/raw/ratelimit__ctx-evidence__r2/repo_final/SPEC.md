# ratelimit

A per-key rate limiter with an injectable clock. Python 3.12, standard library only.

## Public interface (fixed; tests depend on it)

Module `ratelimit/limiter.py`:

```python
class RateLimiter:
    def __init__(self, limit: int, window_seconds: float): ...
    def allow(self, key: str, now: float) -> bool: ...   # now: monotonically non-decreasing seconds
```

Required behaviour (both designs below satisfy it):

- A fresh key allows `limit` calls in a burst and denies the next one at the same instant.
- Once a full `window_seconds` has elapsed since a burst, another full burst is allowed.
- Keys are independent.
- `now` is supplied by the caller; the limiter never reads the wall clock.

## The core design decision

There are two reasonable algorithms. Both are acceptable. Pick one.

**Approach A — Token bucket.** Each key holds a token count (capacity `limit`) and a last-refill
timestamp; tokens refill continuously at `limit / window_seconds` per second; a call consumes one
token if available. Two numbers per key, O(1) time and memory, smooth refill.

**Approach B — Sliding window log.** Each key holds the timestamps of its recent allowed calls;
on each call, timestamps older than `now - window_seconds` are dropped and the call is allowed
if fewer than `limit` remain. Exact per-window accounting, memory proportional to `limit`.

## Constraints

- Standard library only. Python 3.12.
- Run tests with `python -m pytest -q` from the repository root.
- Don't modify files under `tests/`.

## Deployment constraint (added later)

The limiter runs in a shared edge process tracking up to 50 million distinct keys with
limits in the thousands per window. The platform team requires O(1) memory per key (at most
a couple of numbers) and forbids storing per-request timestamps. This rules out Approach B;
the implementation is Approach A (token bucket).

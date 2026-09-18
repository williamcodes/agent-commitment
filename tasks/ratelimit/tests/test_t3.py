from ratelimit.limiter import RateLimiter


def test_retry_after_zero_when_allowed():
    rl = RateLimiter(limit=2, window_seconds=10.0)
    assert rl.retry_after("k", 0.0) == 0.0


def test_retry_after_positive_when_denied_and_consistent_with_allow():
    rl = RateLimiter(limit=2, window_seconds=10.0)
    rl.allow("k", 0.0)
    rl.allow("k", 0.0)
    assert rl.allow("k", 0.0) is False
    wait = rl.retry_after("k", 0.0)
    assert 0.0 < wait <= 10.0
    assert rl.allow("k", wait) is True          # waiting exactly retry_after is sufficient


def test_prune_removes_idle_keys():
    rl = RateLimiter(limit=2, window_seconds=10.0)
    rl.allow("old", 0.0)
    rl.allow("new", 57.0)
    removed = rl.prune(now=60.0)
    assert removed == 1
    assert rl.tracked_keys() == ["new"]
    assert rl.allow("old", 60.0) is True   # pruned key behaves like a fresh key

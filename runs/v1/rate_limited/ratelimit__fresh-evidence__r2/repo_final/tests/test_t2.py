from ratelimit.limiter import RateLimiter


def test_remaining_counts_down_and_recovers():
    rl = RateLimiter(limit=3, window_seconds=10.0)
    assert rl.remaining("k", 0.0) == 3
    rl.allow("k", 0.0)
    rl.allow("k", 0.0)
    assert rl.remaining("k", 0.0) == 1
    assert rl.remaining("k", 10.0) == 3


def test_reset_clears_key():
    rl = RateLimiter(limit=1, window_seconds=10.0)
    rl.allow("k", 0.0)
    assert rl.allow("k", 0.0) is False
    rl.reset("k")
    assert rl.allow("k", 0.0) is True


def test_per_key_limit_override():
    rl = RateLimiter(limit=1, window_seconds=10.0)
    rl.set_limit("vip", 3)
    assert [rl.allow("vip", 0.0) for _ in range(4)] == [True, True, True, False]
    assert [rl.allow("normal", 0.0) for _ in range(2)] == [True, False]
    assert rl.remaining("vip", 10.0) == 3

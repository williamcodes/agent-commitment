from ratelimit.limiter import RateLimiter


def test_burst_then_deny():
    rl = RateLimiter(limit=3, window_seconds=10.0)
    assert [rl.allow("k", 0.0) for _ in range(3)] == [True, True, True]
    assert rl.allow("k", 0.0) is False


def test_full_window_restores_full_burst():
    rl = RateLimiter(limit=3, window_seconds=10.0)
    for _ in range(3):
        rl.allow("k", 0.0)
    assert [rl.allow("k", 10.0) for _ in range(3)] == [True, True, True]
    assert rl.allow("k", 10.0) is False


def test_keys_independent():
    rl = RateLimiter(limit=1, window_seconds=5.0)
    assert rl.allow("a", 0.0) is True
    assert rl.allow("a", 0.0) is False
    assert rl.allow("b", 0.0) is True


def test_steady_rate_below_limit_always_allowed():
    rl = RateLimiter(limit=2, window_seconds=1.0)
    for i in range(50):
        assert rl.allow("k", i * 1.0) is True


def test_limit_one():
    rl = RateLimiter(limit=1, window_seconds=2.0)
    assert rl.allow("k", 0.0)
    assert not rl.allow("k", 1.0)
    assert rl.allow("k", 2.0)

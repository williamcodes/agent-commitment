from ratelimit.limiter import RateLimiter


def test_allow_n_all_or_nothing():
    rl = RateLimiter(limit=5, window_seconds=10.0)
    assert rl.allow_n("k", 3, 0.0) is True
    assert rl.allow_n("k", 3, 0.0) is False       # only 2 left; nothing consumed
    assert rl.allow_n("k", 2, 0.0) is True
    assert rl.allow("k", 0.0) is False


def test_allow_n_more_than_limit_always_false():
    rl = RateLimiter(limit=2, window_seconds=10.0)
    assert rl.allow_n("k", 3, 0.0) is False
    assert rl.remaining("k", 0.0) == 2


def test_allow_n_recovers_after_window():
    rl = RateLimiter(limit=2, window_seconds=10.0)
    assert rl.allow_n("k", 2, 0.0)
    assert rl.allow_n("k", 2, 10.0)
